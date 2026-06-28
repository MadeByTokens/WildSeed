"""Capture several gz camera topics (+ optional lidar) in one sim run."""
import sys, time
import numpy as np
from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image
from gz.msgs10.laserscan_pb2 import LaserScan

cams = sys.argv[1].split(",") if len(sys.argv) > 1 else ["cam_over1", "cam_over2", "cam_ground"]
got = {}
node = Node()

def mk(name):
    def cb(m):
        if name in got:
            return
        raw = np.frombuffer(m.data, dtype=np.uint8)
        got[name] = raw[: m.height * m.width * 3].reshape(m.height, m.width, 3)
        np.save(f"/workspace/frames/{name}.npy", got[name])
    return cb

for c in cams:
    node.subscribe(Image, c, mk(c))

lid = {}
def lcb(m):
    r = np.array(m.ranges, dtype=np.float64)
    f = r[np.isfinite(r)]
    h = f[(f > m.range_min) & (f < m.range_max)]
    lid["s"] = (int(h.size), int(r.size), float(h.min()) if h.size else None, float(h.mean()) if h.size else None)
node.subscribe(LaserScan, "glidar", lcb)

t0 = time.time()
while time.time() - t0 < 50 and not (all(c in got for c in cams) and "s" in lid):
    time.sleep(0.3)

for c in cams:
    if c in got:
        g = ((got[c][:, :, 1] > got[c][:, :, 0] + 12) & (got[c][:, :, 1] > got[c][:, :, 2] + 12)).mean() * 100
        print(f"{c:10s}: {got[c].shape} std={got[c].std():.1f} green%={g:.1f} -> {'NON-BLANK' if got[c].std()>5 else 'BLANK'}", flush=True)
    else:
        print(f"{c:10s}: NO MSG", flush=True)
if "s" in lid:
    s = lid["s"]
    print(f"cam_ground lidar: {s[0]}/{s[1]} returns min={s[2]} mean={s[3]} -> {'RETURNS OK' if s[0]>0 else 'NONE'}", flush=True)
