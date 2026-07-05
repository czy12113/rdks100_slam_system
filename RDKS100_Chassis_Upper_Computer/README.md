# RDKS100 Chassis Upper Computer

This directory contains the RDK S100 upper-computer software for the RDKS100 Ackermann robot. It includes ROS 2 packages, SLAM/navigation launch files, sensor bringup, perception nodes, a FastAPI backend, and a Vue web console.

Chinese documentation: [README_cn.md](README_cn.md)

## Directory Layout

```text
RDKS100_Chassis_Upper_Computer/
+-- backend/                    # FastAPI backend and robot data bridge
+-- frontend/                   # Vue 3 web console source
+-- backend/static/dist/        # Built frontend served by backend
+-- ros2_ws/                    # ROS 2 workspace
+-- fire-smoke-detect-yolov5/   # YOLOv5 fire/smoke detection pipeline
+-- fan-curve/                  # RDK fan control helper
+-- my_map/                     # Map resources
+-- scripts/                    # Runtime helper scripts
+-- build_ros2_ws.sh            # ROS 2 workspace build helper
+-- start.sh                    # Main startup helper
+-- deploy.sh                   # Deployment helper
+-- rdk_slam_setup.sh           # Environment/setup helper
```

## ROS 2 Packages

```text
ros2_ws/src/czybot_slam/         SLAM configuration, launch files, map saving, scan filtering
ros2_ws/src/czybot_navigation2/  Nav2 launch files, Ackermann navigation, STM32 bridge, HMI bridge
ros2_ws/src/d435i_bringup/       Intel RealSense D435i camera bringup
ros2_ws/src/d435i_detection/     Camera detection nodes and fire/smoke parameters
ros2_ws/src/ldlidar_ros2/        LD LiDAR driver and SLAM launch examples
ros2_ws/src/livox_ros_driver2/   Livox ROS 2 driver
ros2_ws/src/vlm_scene/           VLM scene understanding node and providers
```

## Feature Modules

- Web dashboard: CPU, memory, temperature, robot state, logs, and runtime status.
- Robot control: virtual joystick, keyboard control, speed tuning, emergency stop, and odometry display.
- Video and detection: D435i image input, depth-assisted detection, screenshots, fullscreen view, and overlay display.
- LiDAR and SLAM: LD LiDAR or Livox MID-360 point cloud/scan input, Cartographer/SLAM Toolbox workflows, map save/load.
- Navigation: Nav2 integration, Ackermann planning/control configuration, dynamic obstacle and safety-event display.
- VLM scene understanding: cloud and local-provider structure for semantic scene description.
- Fire/smoke alerting: YOLOv5 precheck and VLM confirmation path for frontend alerts.

## Build and Run

```bash
cd RDKS100_Chassis_Upper_Computer
chmod +x build_ros2_ws.sh start.sh deploy.sh rdk_slam_setup.sh
./build_ros2_ws.sh
./start.sh
```

If you only need to build the ROS 2 workspace:

```bash
cd RDKS100_Chassis_Upper_Computer/ros2_ws
colcon build
source install/setup.bash
```

## VLM Provider Configuration

API keys are provided through environment variables:

```bash
export DASHSCOPE_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
```

Optional model and endpoint overrides:

```bash
export VLM_QWEN_MODEL="qwen-vl-plus"
export VLM_QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export VLM_OPENAI_MODEL="gpt-4o-mini"
export VLM_OPENAI_BASE_URL="https://api.openai.com/v1"
```

Key helper:

```text
ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py
```

Example environment file:

```text
.env.example
```

## Common Launch Paths

SLAM and navigation launch files are mainly under:

```text
ros2_ws/src/czybot_slam/launch/
ros2_ws/src/czybot_navigation2/launch/
ros2_ws/src/ldlidar_ros2/launch/
ros2_ws/src/vlm_scene/launch/
```

The exact launch command depends on the sensor combination and operating mode used on the robot.

## License

This project is licensed under the Apache License 2.0. See the repository-level [LICENSE](../LICENSE).
