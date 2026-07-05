# RDKS100 底盘上位机

本目录包含 RDKS100 阿克曼机器人的 RDK S100 上位机软件，包括 ROS 2 包、SLAM/导航启动文件、传感器启动、感知节点、FastAPI 后端和 Vue Web 控制台。

English documentation: [README.md](README.md)

## 目录结构

```text
RDKS100_Chassis_Upper_Computer/
+-- backend/                    # FastAPI 后端与机器人数据桥接
+-- frontend/                   # Vue 3 Web 控制台源码
+-- backend/static/dist/        # 后端直接服务的前端构建产物
+-- ros2_ws/                    # ROS 2 工作空间
+-- fire-smoke-detect-yolov5/   # YOLOv5 烟火检测流程
+-- fan-curve/                  # RDK 风扇控制辅助工具
+-- my_map/                     # 地图资源
+-- scripts/                    # 运行辅助脚本
+-- build_ros2_ws.sh            # ROS 2 工作空间构建脚本
+-- start.sh                    # 主启动脚本
+-- deploy.sh                   # 部署脚本
+-- rdk_slam_setup.sh           # 环境/配置辅助脚本
```

## ROS 2 包

```text
ros2_ws/src/czybot_slam/         SLAM 配置、启动文件、地图保存、scan 过滤
ros2_ws/src/czybot_navigation2/  Nav2 启动文件、阿克曼导航、STM32 bridge、HMI bridge
ros2_ws/src/d435i_bringup/       Intel RealSense D435i 相机启动
ros2_ws/src/d435i_detection/     相机检测节点与烟火检测参数
ros2_ws/src/ldlidar_ros2/        LD LiDAR 驱动与 SLAM 启动示例
ros2_ws/src/livox_ros_driver2/   Livox ROS 2 驱动
ros2_ws/src/vlm_scene/           VLM 场景理解节点和 provider
```

## 功能模块

- Web 控制台：CPU、内存、温度、机器人状态、日志和运行状态。
- 机器人控制：虚拟摇杆、键盘控制、速度调节、急停、里程计显示。
- 视频与检测：D435i 图像输入、深度辅助检测、截图、全屏显示、叠加显示。
- LiDAR 与 SLAM：LD LiDAR 或 Livox MID-360 点云/scan 输入、Cartographer/SLAM Toolbox 流程、地图保存/加载。
- 导航：Nav2 集成、阿克曼规划/控制配置、动态障碍物与安全事件显示。
- VLM 场景理解：云端和本地 provider 结构，用于语义场景描述。
- 烟火告警：YOLOv5 一阶段预检与 VLM 二阶段确认，并推送前端告警。

## 构建与运行

```bash
cd RDKS100_Chassis_Upper_Computer
chmod +x build_ros2_ws.sh start.sh deploy.sh rdk_slam_setup.sh
./build_ros2_ws.sh
./start.sh
```

如果只需要构建 ROS 2 工作空间：

```bash
cd RDKS100_Chassis_Upper_Computer/ros2_ws
colcon build
source install/setup.bash
```

## VLM Provider 配置

API Key 通过环境变量提供：

```bash
export DASHSCOPE_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
```

可选模型和接口覆盖：

```bash
export VLM_QWEN_MODEL="qwen-vl-plus"
export VLM_QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export VLM_OPENAI_MODEL="gpt-4o-mini"
export VLM_OPENAI_BASE_URL="https://api.openai.com/v1"
```

密钥读取辅助文件：

```text
ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py
```

示例环境文件：

```text
.env.example
```

## 常用启动位置

SLAM 和导航启动文件主要位于：

```text
ros2_ws/src/czybot_slam/launch/
ros2_ws/src/czybot_navigation2/launch/
ros2_ws/src/ldlidar_ros2/launch/
ros2_ws/src/vlm_scene/launch/
```

具体启动命令取决于机器人实际使用的传感器组合和运行模式。

## License

本项目使用 Apache License 2.0，详见仓库根目录 [LICENSE](../LICENSE)。
