"""GRAFT helper (the deliverable merge tool) + proof-camera placement.
Reads a WildSeed-generated world, grafts ALL <include> blocks (terrain + vegetation)
into the project's shell (6 gz Harmonic plugins + spherical_coordinates), and adds
proof cameras: two elevated overviews + one ground-level camera auto-aimed at the
densest tree cluster (parsed from the placed tree poses). Writes forest_full.world.
"""
import xml.etree.ElementTree as ET
import numpy as np

SRC = "/workspace/worlds/forest_world.world"
OUT = "/workspace/worlds/forest_full.world"

includes = ET.parse(SRC).getroot().find("world").findall("include")
trees = []
for inc in includes:
    if "model://tree" in inc.findtext("uri", ""):
        p = inc.findtext("pose", "0 0 0 0 0 0").split()
        trees.append([float(p[0]), float(p[1]), float(p[2])])
trees = np.array(trees)

# densest cluster: tree with most neighbours within R
R = 20.0
ci = int(np.argmax([(np.linalg.norm(trees - t, axis=1) < R).sum() for t in trees]))
cluster = trees[np.linalg.norm(trees - trees[ci], axis=1) < R]
cen = cluster.mean(axis=0)
print(f"densest tree cluster: {len(cluster)} trees around "
      f"({cen[0]:.1f},{cen[1]:.1f},{cen[2]:.1f})")

# ground camera: 16 m south of centroid, 2.5 m above local tree base, facing +Y (yaw=pi/2)
gcam = (cen[0], cen[1] - 16.0, cen[2] + 2.5)

SHELL = f'''<?xml version='1.0' encoding='ASCII'?>
<sdf version='1.8'>
  <world name='forest_full'>
    <physics name='1ms' type='ode'><max_step_size>0.003</max_step_size><real_time_factor>1.0</real_time_factor></physics>
    <plugin name='gz::sim::systems::Physics'          filename='gz-sim-physics-system'/>
    <plugin name='gz::sim::systems::UserCommands'     filename='gz-sim-user-commands-system'/>
    <plugin name='gz::sim::systems::SceneBroadcaster' filename='gz-sim-scene-broadcaster-system'/>
    <plugin name='gz::sim::systems::Sensors'          filename='gz-sim-sensors-system'><render_engine>ogre2</render_engine></plugin>
    <plugin name='gz::sim::systems::Imu'    filename='gz-sim-imu-system'/>
    <plugin name='gz::sim::systems::NavSat' filename='gz-sim-navsat-system'/>
    <scene><ambient>0.7 0.7 0.7 1</ambient><background>0.5 0.7 0.92 1</background><grid>false</grid></scene>
    <light name='sun' type='directional'><cast_shadows>1</cast_shadows><pose>0 0 50 0 0 0</pose>
      <diffuse>1 1 1 1</diffuse><specular>0.2 0.2 0.2 1</specular><direction>-0.4 0.3 -0.9</direction></light>
    <spherical_coordinates><surface_model>EARTH_WGS84</surface_model><world_frame_orientation>ENU</world_frame_orientation>
      <latitude_deg>57.0271155</latitude_deg><longitude_deg>-115.426770</longitude_deg><elevation>600</elevation><heading_deg>0</heading_deg></spherical_coordinates>
'''

def cam(name, x, y, z, roll, pitch, yaw, fov=1.1):
    return (f"    <model name='{name}'><static>true</static><pose>{x:.3f} {y:.3f} {z:.3f} {roll} {pitch} {yaw}</pose>"
            f"<link name='link'><sensor name='{name}' type='camera'><topic>{name}</topic>"
            f"<always_on>1</always_on><update_rate>5</update_rate>"
            f"<camera><horizontal_fov>{fov}</horizontal_fov><image><width>800</width><height>600</height></image>"
            f"<clip><near>0.1</near><far>3000</far></clip></camera></sensor>"
            # also a lidar on the ground rig to prove returns off vegetation
            + ("<sensor name='glidar' type='gpu_lidar'><topic>glidar</topic><always_on>1</always_on><update_rate>10</update_rate>"
               "<lidar><scan><horizontal><samples>360</samples><min_angle>-3.14159</min_angle><max_angle>3.14159</max_angle></horizontal>"
               "<vertical><samples>16</samples><min_angle>-0.3</min_angle><max_angle>0.2</max_angle></vertical></scan>"
               "<range><min>0.1</min><max>120</max></range></lidar></sensor>" if name == "cam_ground" else "")
            + "</link></model>\n")

parts = [SHELL]
# graft every include verbatim
for inc in includes:
    parts.append("    " + ET.tostring(inc, encoding="unicode").strip() + "\n")
# overview cameras (oblique + higher) looking at terrain centre
parts.append(cam("cam_over1", 0, -185, 135, 0, 0.52, 1.5708, fov=1.25))
parts.append(cam("cam_over2", -150, -150, 150, 0, 0.6, 0.7854, fov=1.2))
# ground-level robot's-eye view in the densest cluster, facing +Y
parts.append(cam("cam_ground", gcam[0], gcam[1], gcam[2], 0, 0.04, 1.5708, fov=1.2))
parts.append("  </world>\n</sdf>\n")

with open(OUT, "w") as f:
    f.write("".join(parts))
print(f"wrote {OUT}  ({len(includes)} includes grafted)")
print(f"cam_ground at ({gcam[0]:.1f},{gcam[1]:.1f},{gcam[2]:.1f})")
