"""Seeded cinematic trajectories for the sensor rig (SENSOR_RIG_PLAN Phase 2).

Synthesis is pure and deterministic: pattern + seed + terrain -> a list of
timestamped poses written to a trajectory JSON *before* any playback. The seed
defines the file; the file defines the flight. Playback (gz-transport,
kinematic ``set_pose`` paced by SIM time) lives in :func:`play_trajectory` and
imports gz bindings lazily so synthesis works anywhere.

Kinematic playback teleports the body between samples — IMU output is garbage
by construction in this mode (Phase 4's dynamic mode is the honest one); the
trajectory JSON records the mode so datasets can never confuse the two.
"""

import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("wildseed.fly")

PATTERNS = ("orbit", "flythrough", "lawnmower", "dolly")
TRAJECTORY_FORMAT = 1
_PITCH_LIMIT = 0.35          # rad; keeps cinematic shots from nosediving
_Z_SMOOTH_SAMPLES = 51       # odd; ~1.7 s of AGL smoothing at 30 Hz


class TerrainSampler:
    """Fast (x, y) -> ground z from the generated terrain STL.

    Builds one LinearNDInterpolator over the mesh vertices instead of the
    per-query closest-triangle scan used at placement time — trajectory
    synthesis queries thousands of points.
    """

    def __init__(self, stl_path: Path):
        from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
        from stl import mesh as stl_mesh

        m = stl_mesh.Mesh.from_file(str(stl_path))
        pts = m.vectors.reshape(-1, 3)
        # dedup: STL repeats shared vertices per triangle
        xy, idx = np.unique(np.round(pts[:, :2], 4), axis=0, return_index=True)
        z = pts[idx, 2]
        self._lin = LinearNDInterpolator(xy, z)
        self._near = NearestNDInterpolator(xy, z)  # fallback outside the hull
        self.x_min, self.y_min = xy.min(axis=0)
        self.x_max, self.y_max = xy.max(axis=0)

    def height(self, x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        z = self._lin(x, y)
        bad = ~np.isfinite(z)
        if np.any(bad):
            z = np.where(bad, self._near(x, y), z)
        return z

    def bounds(self, margin: float = 0.0):
        return (self.x_min + margin, self.y_min + margin,
                self.x_max - margin, self.y_max - margin)


def _waypoints(pattern: str, rng: np.random.Generator, terrain: TerrainSampler,
               margin: float, center: Optional[Tuple[float, float]],
               radius: Optional[float]) -> np.ndarray:
    """Seeded 2-D waypoints per pattern (z comes later from AGL-following)."""
    x0, y0, x1, y1 = terrain.bounds(margin)
    span = min(x1 - x0, y1 - y0)
    if span <= 0:
        raise ValueError("terrain smaller than twice the margin")
    cx, cy = center if center else ((x0 + x1) / 2, (y0 + y1) / 2)

    if pattern == "orbit":
        r = radius if radius else span * 0.3
        # seeded start azimuth + direction; dense enough that the spline is a circle
        a0 = rng.uniform(0, 2 * math.pi)
        direction = 1 if rng.random() < 0.5 else -1
        angles = a0 + direction * np.linspace(0, 2 * math.pi, 24, endpoint=False)
        pts = np.stack([cx + r * np.cos(angles), cy + r * np.sin(angles)], axis=1)
        return np.vstack([pts, pts[0]])  # close the loop

    if pattern == "flythrough":
        # cross the terrain corner-to-corner-ish with seeded lateral wander
        n = 8
        t = np.linspace(0, 1, n)
        sign = 1 if rng.random() < 0.5 else -1
        xs = x0 + t * (x1 - x0)
        ys = y0 + t * (y1 - y0) if sign > 0 else y1 - t * (y1 - y0)
        wander = rng.normal(0.0, span * 0.08, size=n)
        # wander perpendicular to the diagonal
        xs = xs - wander * (1 / math.sqrt(2)) * sign
        ys = ys + wander * (1 / math.sqrt(2))
        return np.clip(np.stack([xs, ys], axis=1),
                       [x0, y0], [x1, y1])

    if pattern == "lawnmower":
        rows = 4 + int(rng.integers(0, 3))          # 4-6 rows
        width = span * 0.8
        height = span * 0.8
        xs_edge = (cx - width / 2, cx + width / 2)
        pts = []
        for i in range(rows):
            y = cy - height / 2 + height * i / (rows - 1)
            xs_row = xs_edge if i % 2 == 0 else xs_edge[::-1]
            pts.append((xs_row[0], y))
            pts.append((xs_row[1], y))
        return np.array(pts)

    if pattern == "dolly":
        # slow push toward the centre from a seeded bearing
        bearing = rng.uniform(0, 2 * math.pi)
        d0 = span * 0.45
        n = 6
        t = np.linspace(0, 1, n)
        dist = d0 * (1 - t) + span * 0.05 * t
        xs = cx + dist * np.cos(bearing)
        ys = cy + dist * np.sin(bearing)
        return np.stack([xs, ys], axis=1)

    raise ValueError(f"unknown pattern '{pattern}' (choose from {PATTERNS})")


def _yaw_pitch_to_quat(yaw: float, pitch: float) -> Tuple[float, float, float, float]:
    """qw,qx,qy,qz for Rz(yaw)·Ry(pitch) (roll deliberately zero)."""
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    return (cy * cp, -sy * sp, cy * sp, sy * cp)


def synthesize(pattern: str, seed: int, terrain: TerrainSampler,
               speed: float = 5.0, agl: float = 12.0, rate: float = 30.0,
               margin: float = 15.0,
               center: Optional[Tuple[float, float]] = None,
               radius: Optional[float] = None,
               look_at_center: Optional[bool] = None) -> Dict:
    """Synthesize a seeded trajectory dict (JSON-ready, deterministic).

    Same (pattern, seed, terrain, params) -> byte-identical JSON.
    """
    from scipy.interpolate import CubicSpline, PchipInterpolator
    from scipy.ndimage import uniform_filter1d

    if pattern not in PATTERNS:
        raise ValueError(f"unknown pattern '{pattern}' (choose from {PATTERNS})")
    rng = np.random.default_rng(seed)
    wps = _waypoints(pattern, rng, terrain, margin, center, radius)

    # chordal time parameterization at constant target speed
    seg = np.linalg.norm(np.diff(wps, axis=0), axis=1)
    t_wp = np.concatenate([[0.0], np.cumsum(seg)]) / max(speed, 0.1)
    duration = float(t_wp[-1])
    periodic = bool(np.allclose(wps[0], wps[-1]))

    n = max(int(duration * rate), 2)
    t = np.arange(n) / rate
    if periodic:   # orbit: periodic cubic keeps the loop round
        spline = CubicSpline(t_wp, wps, axis=0, bc_type="periodic")
        xy = spline(t)
        vel_xy = spline(t, 1)
    else:          # open paths: PCHIP is shape-preserving — a lawnmower's row
        # turnarounds must not overshoot past the margin the waypoints respect
        spline = PchipInterpolator(t_wp, wps, axis=0)
        xy = spline(t)
        vel_xy = spline.derivative()(t)

    # terrain-following altitude, low-passed so the camera doesn't ride bumps
    ground = terrain.height(xy[:, 0], xy[:, 1])
    z = uniform_filter1d(ground, size=min(_Z_SMOOTH_SAMPLES, n),
                         mode="nearest") + agl
    vz = np.gradient(z, 1.0 / rate)

    # orientation: yaw follows velocity (orbit looks at the centre), pitch gentle
    if look_at_center is None:
        look_at_center = pattern == "orbit"
    if look_at_center:
        cx, cy = center if center else (
            (terrain.x_min + terrain.x_max) / 2,
            (terrain.y_min + terrain.y_max) / 2)
        yaw = np.arctan2(cy - xy[:, 1], cx - xy[:, 0])
    else:
        yaw = np.arctan2(vel_xy[:, 1], vel_xy[:, 0])
    yaw = np.unwrap(yaw)
    h_speed = np.linalg.norm(vel_xy, axis=1)
    pitch = np.clip(-np.arctan2(vz, np.maximum(h_speed, 0.5)),
                    -_PITCH_LIMIT, _PITCH_LIMIT)

    samples: List[Dict] = []
    for i in range(n):
        qw, qx, qy, qz = _yaw_pitch_to_quat(float(yaw[i]), float(pitch[i]))
        samples.append({
            "t": round(float(t[i]), 4),
            "x": round(float(xy[i, 0]), 4), "y": round(float(xy[i, 1]), 4),
            "z": round(float(z[i]), 4),
            "qw": round(qw, 6), "qx": round(qx, 6),
            "qy": round(qy, 6), "qz": round(qz, 6),
        })

    return {
        "format": TRAJECTORY_FORMAT,
        "mode": "kinematic",   # set_pose playback; IMU not meaningful
        "pattern": pattern, "seed": seed,
        "speed": speed, "agl": agl, "rate": rate, "margin": margin,
        "duration": round(duration, 4),
        "count": n,
        "samples": samples,
    }


def write_trajectory(traj: Dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(traj, indent=1))
    return path


def interpolate_pose(traj: Dict, t: float) -> Dict:
    """Linear pose interpolation at time t (clamped to the trajectory)."""
    samples = traj["samples"]
    rate = traj["rate"]
    if t <= samples[0]["t"]:
        return samples[0]
    if t >= samples[-1]["t"]:
        return samples[-1]
    i = min(int(t * rate), len(samples) - 2)
    a, b = samples[i], samples[i + 1]
    if not (a["t"] <= t <= b["t"]):   # guard vs rounding
        i = next(j for j in range(len(samples) - 1)
                 if samples[j]["t"] <= t <= samples[j + 1]["t"])
        a, b = samples[i], samples[i + 1]
    w = (t - a["t"]) / max(b["t"] - a["t"], 1e-9)
    out = {k: a[k] + w * (b[k] - a[k]) for k in ("x", "y", "z")}
    # nlerp is fine at 30 Hz sample spacing
    q = np.array([a["qw"] + w * (b["qw"] - a["qw"]),
                  a["qx"] + w * (b["qx"] - a["qx"]),
                  a["qy"] + w * (b["qy"] - a["qy"]),
                  a["qz"] + w * (b["qz"] - a["qz"])])
    q = q / np.linalg.norm(q)
    out.update({"qw": q[0], "qx": q[1], "qy": q[2], "qz": q[3]})
    return out


def play_trajectory(traj: Dict, world: str = "forest_world",
                    model: str = "sensor_rig", update_hz: float = 50.0,
                    settle_s: float = 2.0) -> int:
    """Drive the model along the trajectory, paced by SIM time (gz-transport).

    Runs inside the containers (needs gz.transport13). Returns the number of
    set_pose calls issued. Never paces by wall clock: the sim may run slower
    or faster than real time and the flight must not care.
    """
    import time

    from gz.msgs10.boolean_pb2 import Boolean
    from gz.msgs10.pose_pb2 import Pose
    from gz.msgs10.world_stats_pb2 import WorldStatistics
    from gz.transport13 import Node

    node = Node()
    # /world/<w>/stats publishes at ~5 Hz (and /clock is silent headless —
    # measured); pacing on raw stats quantizes the flight into 0.2 s pose
    # jumps. Extrapolate between ticks with the reported real-time factor.
    sim = {"t": None, "wall": None, "rtf": 1.0}

    def stats_cb(msg):
        sim["t"] = msg.sim_time.sec + msg.sim_time.nsec * 1e-9
        sim["wall"] = time.time()
        if msg.real_time_factor > 0:
            sim["rtf"] = msg.real_time_factor

    def sim_now():
        return sim["t"] + (time.time() - sim["wall"]) * sim["rtf"]

    node.subscribe(WorldStatistics, f"/world/{world}/stats", stats_cb)
    deadline = time.time() + 30
    while sim["t"] is None:
        if time.time() > deadline:
            raise RuntimeError(f"no sim clock on /world/{world}/stats in 30 s "
                               "(is the server running with -r?)")
        time.sleep(0.05)
    time.sleep(settle_s)   # let sensors warm up before the take starts

    service = f"/world/{world}/set_pose"
    t0 = sim_now()
    end_t = traj["samples"][-1]["t"]
    calls = 0
    logger.info(f"playback: {traj['pattern']} seed={traj['seed']} "
                f"{end_t:.1f}s sim, service={service}")
    # Rate-limit the commanded trajectory time: if the sim stalls (sensor
    # init, scene load) the wall-clock extrapolation overruns and would snap
    # the pose metres ahead on the next tick. Monotonic + bounded advance
    # turns any such glitch into a momentary slow-down instead of a jump.
    t_prev = 0.0
    max_advance = 4.0 / update_hz
    while True:
        t = min(max(sim_now() - t0, t_prev), t_prev + max_advance)
        t_prev = t
        p = interpolate_pose(traj, t)
        req = Pose()
        req.name = model
        req.position.x, req.position.y, req.position.z = p["x"], p["y"], p["z"]
        req.orientation.w = p["qw"]
        req.orientation.x = p["qx"]
        req.orientation.y = p["qy"]
        req.orientation.z = p["qz"]
        ok, rep = node.request(service, req, Pose, Boolean, 1000)
        if not (ok and rep.data):
            logger.warning(f"set_pose rejected at t={t:.2f}")
        calls += 1
        if t >= end_t:
            break
        time.sleep(1.0 / update_hz)
    return calls
