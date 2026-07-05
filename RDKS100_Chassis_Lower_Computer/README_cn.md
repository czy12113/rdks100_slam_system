# RDKS100 底盘下位机

本目录包含 RDKS100 阿克曼底盘的 STM32 固件。下位机接收 RDK S100 上位机下发的控制命令，控制转向舵机和电机驱动，并通过串口协议回传里程计与底盘状态。

English documentation: [README.md](README.md)

## 目录结构

```text
RDKS100_Chassis_Lower_Computer/
+-- CORE/                 # Cortex-M 启动与内核支持
+-- RTE/                  # Keil RTE 配置
+-- STM32F10x_FWLib/      # STM32F10x 标准外设库
+-- USER/                 # 底盘业务代码
+-- OpenArmSTM32.uvprojx  # Keil 工程
+-- STM32_Motor.uvprojx   # Keil 工程
```

## 主要模块

```text
USER/main.c                 当前正式运行入口
USER/ROS2Protocol.c/h       上位机使用的串口协议
USER/AckermannControl.c/h   阿克曼转向与运动控制
USER/Odometry.c/h           里程计计算与状态回传
USER/ChassisParams.h        底盘几何和控制参数
USER/SerialControl.c/h      串口命令处理
USER/Motor.c/h              电机控制
USER/Servo.c/h              转向舵机控制
USER/I2CMotor.c/h           I2C 电机驱动接口
USER/Usart.c/h              USART 初始化与通信
```

## 编译

1. 使用 Keil MDK 打开 `OpenArmSTM32.uvprojx` 或 `STM32_Motor.uvprojx`。
2. 确认芯片、串口、定时器、波特率和底盘参数与实际硬件一致。
3. 编译工程。
4. 将固件烧录到 STM32 控制板。
5. 上位机通过配置好的串口与下位机通信。

## 硬件接口

具体接线应以本目录内的硬件文档为准：

```text
硬件接线文档.md
底盘参数说明.md
RDK_ROS2参数配置文档.md
ROS2模式使用说明.md
串口控制使用说明.md
```

## 运行职责

- 解析上位机下发的运动控制命令。
- 将速度命令转换为阿克曼转向和电机输出。
- 根据底盘参数维护里程计。
- 通过串口协议向 ROS 2 回传底盘状态。
- 在控制链路中提供急停和安全停车能力。

## License

本项目使用 Apache License 2.0，详见仓库根目录 [LICENSE](../LICENSE)。
