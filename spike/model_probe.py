"""Build a tiny world with ONE model + a flat ground + a 3/4 camera, to eyeball a
freshly converted asset (esp. foliage alpha).

  MODEL=tree/fir_sapling python3 spike/model_probe.py   # writes worlds/probe.world
The MODEL value is model://<name>; we look up its size from the glb's dir name.
"""
import os

model = os.environ.get("MODEL", "tree/island_tree_01")  # category/name
name = model.split("/")[-1]
uri = f"model://{model}"  # gz resolves category/name under GZ_SIM_RESOURCE_PATH
# camera framing: stand back and a bit up, look slightly down at the model centre
world = f'''<?xml version='1.0' encoding='ASCII'?>
<sdf version='1.8'>
  <world name='probe'>
    <physics name='1ms' type='ode'><max_step_size>0.003</max_step_size><real_time_factor>1.0</real_time_factor></physics>
    <plugin name='gz::sim::systems::Physics'          filename='gz-sim-physics-system'/>
    <plugin name='gz::sim::systems::UserCommands'     filename='gz-sim-user-commands-system'/>
    <plugin name='gz::sim::systems::SceneBroadcaster' filename='gz-sim-scene-broadcaster-system'/>
    <plugin name='gz::sim::systems::Sensors'          filename='gz-sim-sensors-system'><render_engine>ogre2</render_engine></plugin>
    <scene><ambient>0.55 0.55 0.55 1</ambient><background>0.78 0.86 0.94 1</background><grid>false</grid></scene>
    <light name='sun' type='directional'><cast_shadows>1</cast_shadows><pose>0 0 30 0 0 0</pose>
      <diffuse>1 1 1 1</diffuse><specular>0.3 0.3 0.3 1</specular><direction>-0.5 0.3 -0.8</direction></light>
    <model name='floor'><static>true</static><link name='l'><visual name='v'>
      <geometry><plane><normal>0 0 1</normal><size>60 60</size></plane></geometry>
      <material><ambient>0.33 0.30 0.24 1</ambient><diffuse>0.40 0.36 0.28 1</diffuse></material>
    </visual></link></model>
    <include><name>{name}</name><uri>{uri}</uri><pose>0 0 0 0 0 0</pose></include>
    <model name='cam'><static>true</static><pose>9 -9 6 0 0.42 2.356</pose>
      <link name='l'><sensor name='cam' type='camera'><topic>cam</topic><always_on>1</always_on><update_rate>5</update_rate>
        <camera><horizontal_fov>1.05</horizontal_fov><image><width>900</width><height>900</height></image>
        <clip><near>0.05</near><far>500</far></clip></camera></sensor></link></model>
  </world>
</sdf>'''
open("/workspace/worlds/probe.world", "w").write(world)
print("wrote worlds/probe.world for model://%s" % name)
