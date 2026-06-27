#!/usr/bin/env python3
"""Capture one camera frame from a running gz sim via gz-transport (no ROS).
Saves .npy + .ppm and prints pixel stats. A near-zero std-dev => blank frame.
Usage: capture_cam.py <topic> [out_basename]
"""
import sys, time
import numpy as np
from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image

topic = sys.argv[1] if len(sys.argv) > 1 else "spike_camera"
out = sys.argv[2] if len(sys.argv) > 2 else "/workspace/frames/cam"
got = {}

def cb(msg):
    if got:
        return
    h, w = msg.height, msg.width
    raw = np.frombuffer(msg.data, dtype=np.uint8)
    got["img"] = raw
    got["hw"] = (h, w)
    got["pf"] = msg.pixel_format_type
    got["step"] = msg.step

node = Node()
ok = node.subscribe(Image, topic, cb)
print(f"subscribe({topic}) -> {ok}", flush=True)
t0 = time.time()
while not got and time.time() - t0 < 45:
    time.sleep(0.2)
if not got:
    print("NO FRAME RECEIVED", flush=True)
    sys.exit(2)

h, w = got["hw"]
raw = got["img"]
ch = max(1, raw.size // (h * w))
img = raw[: h * w * ch].reshape(h, w, ch)
print(f"FRAME shape={img.shape} pixel_format={got['pf']} step={got['step']}", flush=True)
print(f"STATS mean={img.mean():.3f} std={img.std():.3f} "
      f"min={int(img.min())} max={int(img.max())}", flush=True)
np.save(out + ".npy", img)
rgb = img[:, :, :3] if ch >= 3 else np.repeat(img, 3, axis=2)
with open(out + ".ppm", "wb") as f:
    f.write(f"P6\n{w} {h}\n255\n".encode())
    f.write(np.ascontiguousarray(rgb).tobytes())
print(f"saved {out}.ppm and {out}.npy", flush=True)
# verdict
print("VERDICT:", "NON-BLANK (real render)" if img.std() > 5 else "BLANK/uniform", flush=True)
