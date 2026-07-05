# RDKS100 SLAM System

The RDKS100 System is an intelligent inspection management system targeting large supermarket warehouses, furniture retail warehouses, storage parks and indoor logistics transfer zones. Taking the RDKS100 edge computing platform as the upper computer and STM32F103 as the lower computer for chassis control, the work integrates an Ackermann steering mobile chassis, Livox Mid-360S 3D LiDAR, Intel RealSense D435i RGB-D camera, YOLOv5 object detection, VLM vision-language understanding, Cartographer SLAM and Nav2 navigation, forming a closed-loop warehouse inspection system featuring autonomous patrol, anomaly identification, remote management and control, safe emergency parking and event record retention.
Warehouse environments feature dense shelves, narrow aisles, mixed flow of personnel and vehicles, concentrated combustibles such as cartons and wood boards, high costs for night shift duty, and anomaly detection relying on manual experience. The RDKS100 System uses mobile robots as mobile perception nodes on warehouse sites. It can patrol main aisles, shelf ends, loading and unloading areas, fire passages and high-risk stacking areas along preset routes. It identifies fire and smoke, aisle occupation, personnel approaching, obstacle occlusion and on-site anomaly descriptions through RGB-D images and VLM semantic understanding. The web upper computer displays videos, point clouds, maps, paths, alarms and device status to managers.
The system highlights four innovations: lightweight local VLM can still coordinate with Nav2 to complete identification, detour and alarms when the public network is disconnected; heterogeneous coordination of the cerebellum, mid-core and brain realizes layered deployment of hard real-time control, robot services and AI reasoning; 2D SLAM maps can be converted into editable grid semantic maps for the front end; operators can input natural language tasks via web pages or voice, and VLM combines real-time images and map semantics to decompose tasks and call Nav2 for segmented execution.

Chinese documentation: [README_cn.md](README_cn.md)

## Repository Layout

```text
rdks100_slam_system/
+-- RDKS100_Chassis_Upper_Computer/   # RDK S100, ROS 2 workspace, backend, frontend, perception
+-- RDKS100_Chassis_Lower_Computer/   # STM32 firmware, Keil projects, chassis control
+-- README.md                         # English overview
+-- README_cn.md                      # Chinese overview
+-- LICENSE                           # Apache-2.0 license
```

## System Overview

The project is split into two cooperating parts:

| Directory | Role | Main Content |
|---|---|---|
| `RDKS100_Chassis_Upper_Computer` | Upper computer | ROS 2 workspace, SLAM/navigation launch files, FastAPI backend, Vue dashboard, D435i/LiDAR/VLM/fire-smoke perception |
| `RDKS100_Chassis_Lower_Computer` | Lower computer | STM32F10x firmware, Keil project files, Ackermann control, motor/servo control, serial protocol, odometry |

The upper computer sends chassis commands through the configured serial protocol. The STM32 lower computer executes steering and motor control, then reports odometry and chassis state back to the upper computer.

## Main Features

- ROS 2 workspace for LiDAR SLAM, Nav2 navigation, D435i camera bringup, Livox MID-360 support, and VLM scene nodes.
- FastAPI backend and Vue frontend for dashboard monitoring, map display, robot control, navigation, video, and safety alerts.
- Fire/smoke detection pipeline based on YOLOv5.
- VLM scene understanding through DashScope/Qwen-VL, OpenAI-compatible APIs, DeepSeek text fallback, local placeholder provider, or mock provider.
- STM32 firmware for Ackermann steering, motor control, serial protocol, odometry, and chassis parameter configuration.

## Hardware

- RDK S100 upper computer
- STM32 lower controller
- Ackermann chassis with motor driver and steering servo
- LD14P or Livox MID-360 LiDAR, depending on the selected launch path
- Intel RealSense D435i camera

## Upper Computer

Path:

```text
RDKS100_Chassis_Upper_Computer/
```

Important subdirectories:

```text
backend/                    FastAPI backend and robot data bridge
frontend/                   Vue 3 web console source
backend/static/dist/        Built frontend served by backend
ros2_ws/                    ROS 2 workspace
ros2_ws/src/czybot_slam/    SLAM launch/config/scripts
ros2_ws/src/czybot_navigation2/ Nav2, STM32 bridge, HMI, Ackermann navigation
ros2_ws/src/d435i_bringup/  RealSense D435i camera bringup
ros2_ws/src/d435i_detection/ Detection nodes
ros2_ws/src/vlm_scene/      VLM scene understanding package
fire-smoke-detect-yolov5/   Fire/smoke YOLOv5 pipeline and weights
fan-curve/                  RDK fan control helper
```

Basic build and run:

```bash
cd RDKS100_Chassis_Upper_Computer
chmod +x build_ros2_ws.sh start.sh deploy.sh rdk_slam_setup.sh
./build_ros2_ws.sh
./start.sh
```

VLM providers read keys from environment variables:

```bash
export DASHSCOPE_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
```

Key helper:

```text
RDKS100_Chassis_Upper_Computer/ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py
```

See the upper-computer README for module-level details:

```text
RDKS100_Chassis_Upper_Computer/README.md
RDKS100_Chassis_Upper_Computer/README_cn.md
```

## Lower Computer

Path:

```text
RDKS100_Chassis_Lower_Computer/
```

Important files and modules:

```text
OpenArmSTM32.uvprojx        Keil project
STM32_Motor.uvprojx         Keil project
CORE/                       Cortex-M startup and core support
RTE/                        Keil RTE configuration
STM32F10x_FWLib/            STM32F10x Standard Peripheral Library
USER/main.c                 Current runtime entry point
USER/ROS2Protocol.c/h       Upper/lower computer serial protocol
USER/AckermannControl.c/h   Ackermann chassis control
USER/Odometry.c/h           Odometry calculation and reporting
USER/ChassisParams.h        Chassis geometry and control parameters
USER/Motor.c/h              Motor control
USER/Servo.c/h              Steering servo control
```

Build with Keil MDK:

1. Open `OpenArmSTM32.uvprojx` or `STM32_Motor.uvprojx`.
2. Confirm chip, serial port, timer, and chassis parameters for the actual hardware.
3. Build and flash the firmware to the STM32 controller.
4. Connect the upper computer through the configured serial interface.

See the lower-computer README for firmware-level details:

```text
RDKS100_Chassis_Lower_Computer/README.md
RDKS100_Chassis_Lower_Computer/README_cn.md
```

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE).
