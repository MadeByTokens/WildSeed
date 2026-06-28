"""Build a reference-style hero scene: grass terrain + hero trees + boulders,
with a low robot's-eye camera that frames the largest boulder in the foreground
and the acacias beyond (echoing Screenshot 2026-01-08)."""
import xml.etree.ElementTree as ET
import math

SRC = "/workspace/worlds/forest_world.world"
OUT = "/workspace/worlds/hero_scene.world"

includes = ET.parse(SRC).getroot().find("world").findall("include")
rocks, trees = [], []
for inc in includes:
    uri = inc.findtext("uri", "")
    p = inc.findtext("pose", "0 0 0 0 0 0").split()
    s = float((inc.findtext("scale", "1 1 1").split() or ["1"])[0])
    pose = (float(p[0]), float(p[1]), float(p[2]), s)
    if "model://rock" in uri:
        rocks.append(pose)
    elif "model://tree" in uri:
        trees.append(pose)

def near_trees(r, radius=55.0):
    return [t for t in trees if math.hypot(t[0] - r[0], t[1] - r[1]) < radius]

# foreground boulder = rock with the most nearby trees (compose rock + acacias together)
R = max(rocks, key=lambda r: (len(near_trees(r)), r[3]))
rx, ry, rz, rs = R
local = near_trees(R) or trees
tx = sum(t[0] for t in local) / len(local)
ty = sum(t[1] for t in local) / len(local)
print(f"chosen boulder has {len(near_trees(R))} trees within 55 m")
# Terrain centre is the hilltop; stand OUTWARD of the boulder looking INWARD/uphill
# so the green slope (not sky) fills the background, echoing the reference framing.
onorm = math.hypot(rx, ry) or 1.0
ox, oy = rx / onorm, ry / onorm      # outward (away from hill centre)
px, py = -oy, ox                      # perpendicular (lateral)
rad = 1.9 * rs * 0.6
cx = rx + ox * (6.0 + rad) + px * 2.0
cy = ry + oy * (6.0 + rad) + py * 2.0
cz = rz + 1.6
# aim just past the boulder toward the local trees / uphill, slightly down onto the scene
ax = rx - ox * 6.0 + (tx - rx) * 0.25
ay = ry - oy * 6.0 + (ty - ry) * 0.25
az = rz + 0.8
yaw = math.atan2(ay - cy, ax - cx)
pitch = -math.atan2(az - cz, math.hypot(ax - cx, ay - cy))
print(f"boulder R=({rx:.1f},{ry:.1f},{rz:.1f}) scale={rs:.2f}; cam=({cx:.1f},{cy:.1f},{cz:.1f}) yaw={yaw:.2f} pitch={pitch:.2f}")

SHELL = f'''<?xml version='1.0' encoding='ASCII'?>
<sdf version='1.8'>
  <world name='hero_scene'>
    <physics name='1ms' type='ode'><max_step_size>0.003</max_step_size><real_time_factor>1.0</real_time_factor></physics>
    <plugin name='gz::sim::systems::Physics'          filename='gz-sim-physics-system'/>
    <plugin name='gz::sim::systems::UserCommands'     filename='gz-sim-user-commands-system'/>
    <plugin name='gz::sim::systems::SceneBroadcaster' filename='gz-sim-scene-broadcaster-system'/>
    <plugin name='gz::sim::systems::Sensors'          filename='gz-sim-sensors-system'><render_engine>ogre2</render_engine></plugin>
    <scene><ambient>0.5 0.5 0.5 1</ambient><background>0.78 0.86 0.94 1</background><grid>false</grid></scene>
    <light name='sun' type='directional'><cast_shadows>1</cast_shadows><pose>0 0 50 0 0 0</pose>
      <diffuse>1 1 1 1</diffuse><specular>0.2 0.2 0.2 1</specular><direction>-0.4 0.3 -0.9</direction></light>
'''
parts = [SHELL]
for inc in includes:
    parts.append("    " + ET.tostring(inc, encoding="unicode").strip() + "\n")
parts.append(
    f"    <model name='cam_scene'><static>true</static><pose>{cx:.3f} {cy:.3f} {cz:.3f} 0 {pitch:.4f} {yaw:.4f}</pose>"
    f"<link name='link'><sensor name='cam_scene' type='camera'><topic>cam_scene</topic>"
    f"<always_on>1</always_on><update_rate>5</update_rate>"
    f"<camera><horizontal_fov>1.15</horizontal_fov><image><width>1100</width><height>750</height></image>"
    f"<clip><near>0.1</near><far>3000</far></clip></camera></sensor></link></model>\n")
parts.append("  </world>\n</sdf>\n")
open(OUT, "w").write("".join(parts))
print("wrote", OUT)
