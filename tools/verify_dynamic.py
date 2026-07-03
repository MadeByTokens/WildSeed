#!/usr/bin/env python3
"""Phase-4 gate (docs/SENSOR_RIG_PLAN.md): verdict the DYNAMIC flight mode.

Records IMU + odometry while `wildseed fly --mode dynamic --play` runs in
another process, then verdicts:
  hover   - before the flight starts: |accel| ~= 9.81 (specific force at rest)
  flight  - accel spike-free (kinematic set_pose flight fails this by
            construction: teleports produce delta-function accelerations)
  motion  - the rig actually flew (path length)
Run inside wildseed/wildseed:egl next to a running rig world.
"""
import os
import sys
import time

import numpy as np
from gz.transport13 import Node
from gz.msgs10.imu_pb2 import IMU
from gz.msgs10.odometry_pb2 import Odometry

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
MODEL = os.environ.get("RIG_MODEL", "sensor_rig")
imu_rows, odom_rows = [], []
node = Node()


def imu_cb(m):
    t = m.header.stamp.sec + m.header.stamp.nsec * 1e-9
    imu_rows.append((t, m.linear_acceleration.x, m.linear_acceleration.y,
                     m.linear_acceleration.z))


def odom_cb(m):
    t = m.header.stamp.sec + m.header.stamp.nsec * 1e-9
    p = m.pose.position
    odom_rows.append((t, p.x, p.y, p.z))


node.subscribe(IMU, "rig/imu", imu_cb)
node.subscribe(Odometry, f"/model/{MODEL}/odometry", odom_cb)
time.sleep(DUR)

imu = np.array(imu_rows)
odom = np.array(odom_rows)
if len(imu) < 100 or len(odom) < 100:
    print(f"VERDICT FAIL: imu={len(imu)} odom={len(odom)} msgs")
    sys.exit(1)

acc = np.linalg.norm(imu[:, 1:4], axis=1)
# hover window: first second of IMU data (verifier starts before the flight)
t_rel = imu[:, 0] - imu[0, 0]
hover = acc[t_rel < 1.0]
flight = acc[t_rel >= 3.0]
path = np.linalg.norm(np.diff(odom[:, 1:4], axis=0), axis=1).sum()

hover_ok = len(hover) > 10 and abs(hover.mean() - 9.81) < 0.3 and hover.std() < 0.3
spike_ok = len(flight) > 100 and flight.max() < 25.0 and \
    np.percentile(flight, 99) < 16.0
motion_ok = path > 20.0

print(f"hover  : |acc| mean={hover.mean():.2f} std={hover.std():.3f} "
      f"(n={len(hover)}) -> {'PASS' if hover_ok else 'FAIL'}")
print(f"flight : |acc| p50={np.percentile(flight, 50):.2f} "
      f"p99={np.percentile(flight, 99):.2f} max={flight.max():.2f} "
      f"(n={len(flight)}) -> {'PASS' if spike_ok else 'FAIL'}")
print(f"motion : path={path:.1f} m -> {'PASS' if motion_ok else 'FAIL'}")
ok = hover_ok and spike_ok and motion_ok
print(f"VERDICT {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
