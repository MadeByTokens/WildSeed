#!/usr/bin/env python3
"""Subscribe to camera+lidar+navsat from a running gz sim (gz-transport, no ROS),
report stats, and verdict each. Proves the merged world hosts working sensors."""
import time
import numpy as np
from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image
from gz.msgs10.laserscan_pb2 import LaserScan
from gz.msgs10.navsat_pb2 import NavSat

got = {}
node = Node()

def cam_cb(m):
    if "cam" in got:
        return
    raw = np.frombuffer(m.data, dtype=np.uint8)
    img = raw[: m.height * m.width * 3].reshape(m.height, m.width, 3)
    got["cam"] = img
    np.save("/workspace/frames/spike_cam.npy", img)

def lidar_cb(m):
    r = np.array(m.ranges, dtype=np.float64)
    finite = r[np.isfinite(r)]
    hits = finite[(finite > m.range_min) & (finite < m.range_max)]
    got["lidar"] = dict(n=len(r), hits=int(hits.size),
                        rmin=float(hits.min()) if hits.size else None,
                        rmean=float(hits.mean()) if hits.size else None,
                        rmax=float(hits.max()) if hits.size else None)

def navsat_cb(m):
    got["navsat"] = dict(lat=m.latitude_deg, lon=m.longitude_deg, alt=m.altitude)

node.subscribe(Image, "spike_camera", cam_cb)
node.subscribe(LaserScan, "spike_lidar", lidar_cb)
node.subscribe(NavSat, "spike_navsat", navsat_cb)

t0 = time.time()
while time.time() - t0 < 45 and not (("cam" in got) and ("lidar" in got) and ("navsat" in got)):
    time.sleep(0.2)

print("=== RESULTS ===", flush=True)
if "cam" in got:
    img = got["cam"]
    print(f"CAMERA  : {img.shape} std={img.std():.2f} -> "
          f"{'NON-BLANK' if img.std() > 5 else 'BLANK'}", flush=True)
else:
    print("CAMERA  : NO MSG", flush=True)
if "lidar" in got:
    L = got["lidar"]
    print(f"LIDAR   : {L['hits']}/{L['n']} returns  "
          f"range[min/mean/max]={L['rmin']}/{L['rmean']}/{L['rmax']} -> "
          f"{'RETURNS OK' if L['hits'] > 0 else 'NO RETURNS'}", flush=True)
else:
    print("LIDAR   : NO MSG", flush=True)
if "navsat" in got:
    N = got["navsat"]
    print(f"NAVSAT  : lat={N['lat']:.6f} lon={N['lon']:.6f} alt={N['alt']:.2f} -> "
          f"{'FIX OK' if abs(N['lat']) > 1e-6 else 'NO FIX'}", flush=True)
else:
    print("NAVSAT  : NO MSG", flush=True)
