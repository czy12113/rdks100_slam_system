# RDKS100 SLAM 系统

RDKS100 SLAM System 是一套面向阿克曼底盘的上位机 + 下位机完整机器人项目。上位机运行在 RDK S100 上，负责 ROS 2、SLAM、Nav2、感知、VLM 场景理解和 Web 控制台；下位机运行 STM32 固件，负责底盘运动控制、转向、电机、串口通信和里程计。

English documentation: [README.md](README.md)

## 仓库结构

```text
rdks100_slam_system/
+-- RDKS100_Chassis_Upper_Computer/   # RDK S100、ROS 2 工作空间、后端、前端、感知
+-- RDKS100_Chassis_Lower_Computer/   # STM32 固件、Keil 工程、底盘控制
+-- README.md                         # 英文总览
+-- README_cn.md                      # 中文总览
+-- LICENSE                           # Apache-2.0 许可证
```

## 系统说明

本项目由两个协同工作的部分组成：

| 目录 | 作用 | 主要内容 |
|---|---|---|
| `RDKS100_Chassis_Upper_Computer` | 上位机 | ROS 2 工作空间、SLAM/导航启动文件、FastAPI 后端、Vue 控制台、D435i/LiDAR/VLM/烟火检测感知 |
| `RDKS100_Chassis_Lower_Computer` | 下位机 | STM32F10x 固件、Keil 工程、阿克曼控制、电机/舵机控制、串口协议、里程计 |

上位机通过配置好的串口协议向下位机发送底盘控制命令。STM32 下位机执行转向和电机控制，并把里程计与底盘状态回传给上位机。

## 主要功能

- ROS 2 工作空间：LiDAR SLAM、Nav2 导航、D435i 相机启动、Livox MID-360 支持、VLM 场景节点。
- FastAPI 后端 + Vue 前端：综合监控、地图显示、机器人控制、导航、视频、安全告警。
- 基于 YOLOv5 的烟火检测流程。
- VLM 场景理解：支持 DashScope/Qwen-VL、OpenAI 兼容接口、DeepSeek 文本兜底、本地占位 provider、mock provider。
- STM32 固件：阿克曼转向、电机控制、串口协议、里程计、底盘参数配置。

## 硬件组成

- RDK S100 上位机
- STM32 下位机控制板
- 阿克曼底盘、电机驱动、转向舵机
- LD14P 或 Livox MID-360 雷达，取决于实际启动路径
- Intel RealSense D435i 相机

## 上位机说明

路径：

```text
RDKS100_Chassis_Upper_Computer/
```

重要子目录：

```text
backend/                         FastAPI 后端与机器人数据桥接
frontend/                        Vue 3 Web 控制台源码
backend/static/dist/             后端直接服务的前端构建产物
ros2_ws/                         ROS 2 工作空间
ros2_ws/src/czybot_slam/         SLAM 启动、配置和脚本
ros2_ws/src/czybot_navigation2/  Nav2、STM32 bridge、HMI、阿克曼导航
ros2_ws/src/d435i_bringup/       RealSense D435i 相机启动
ros2_ws/src/d435i_detection/     检测节点
ros2_ws/src/vlm_scene/           VLM 场景理解包
fire-smoke-detect-yolov5/        烟火检测 YOLOv5 流程和权重
fan-curve/                       RDK 风扇控制辅助工具
```

基础构建与运行：

```bash
cd RDKS100_Chassis_Upper_Computer
chmod +x build_ros2_ws.sh start.sh deploy.sh rdk_slam_setup.sh
./build_ros2_ws.sh
./start.sh
```

VLM provider 通过环境变量读取密钥：

```bash
export DASHSCOPE_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
```

密钥读取辅助文件：

```text
RDKS100_Chassis_Upper_Computer/ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py
```

上位机目录内还有独立 README，包含模块级说明：

```text
RDKS100_Chassis_Upper_Computer/README.md
RDKS100_Chassis_Upper_Computer/README_cn.md
```

## 下位机说明

路径：

```text
RDKS100_Chassis_Lower_Computer/
```

重要文件与模块：

```text
OpenArmSTM32.uvprojx             Keil 工程
STM32_Motor.uvprojx              Keil 工程
CORE/                            Cortex-M 启动与内核支持
RTE/                             Keil RTE 配置
STM32F10x_FWLib/                 STM32F10x 标准外设库
USER/main.c                      当前正式运行入口
USER/ROS2Protocol.c/h            上下位机串口协议
USER/AckermannControl.c/h        阿克曼底盘控制
USER/Odometry.c/h                里程计计算与回传
USER/ChassisParams.h             底盘几何和控制参数
USER/Motor.c/h                   电机控制
USER/Servo.c/h                   转向舵机控制
```

使用 Keil MDK 编译：

1. 打开 `OpenArmSTM32.uvprojx` 或 `STM32_Motor.uvprojx`。
2. 确认目标芯片、串口、定时器和底盘参数与实际硬件一致。
3. 编译工程并烧录到 STM32 控制板。
4. 上位机通过配置好的串口与下位机通信。

下位机目录内还有独立 README，包含固件级说明：

```text
RDKS100_Chassis_Lower_Computer/README.md
RDKS100_Chassis_Lower_Computer/README_cn.md
```

## License

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE)。
