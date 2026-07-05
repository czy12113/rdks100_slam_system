# RDKS100 Chassis Lower Computer

This directory contains the STM32 firmware for the RDKS100 Ackermann chassis. The lower computer receives commands from the RDK S100 upper computer, controls the steering servo and motor driver, and reports odometry and chassis state through the serial protocol.

Chinese documentation: [README_cn.md](README_cn.md)

## Directory Layout

```text
RDKS100_Chassis_Lower_Computer/
+-- CORE/                 # Cortex-M startup and core support
+-- RTE/                  # Keil RTE configuration
+-- STM32F10x_FWLib/      # STM32F10x Standard Peripheral Library
+-- USER/                 # Chassis application code
+-- OpenArmSTM32.uvprojx  # Keil project
+-- STM32_Motor.uvprojx   # Keil project
```

## Main Modules

```text
USER/main.c                 Current runtime entry point
USER/ROS2Protocol.c/h       Serial protocol used by the upper computer
USER/AckermannControl.c/h   Ackermann steering and motion control
USER/Odometry.c/h           Odometry calculation and state reporting
USER/ChassisParams.h        Chassis geometry and control parameters
USER/SerialControl.c/h      Serial command handling
USER/Motor.c/h              Motor control
USER/Servo.c/h              Steering servo control
USER/I2CMotor.c/h           I2C motor driver interface
USER/Usart.c/h              USART initialization and communication
```

## Build

1. Open `OpenArmSTM32.uvprojx` or `STM32_Motor.uvprojx` with Keil MDK.
2. Confirm that chip, serial port, timer, baud rate, and chassis parameters match the actual hardware.
3. Build the project.
4. Flash the firmware to the STM32 controller.
5. Connect the upper computer through the configured serial interface.

## Hardware Interface

The exact wiring should follow the project hardware documentation in this directory:

```text
硬件接线文档.md
底盘参数说明.md
RDK_ROS2参数配置文档.md
ROS2模式使用说明.md
串口控制使用说明.md
```

## Runtime Role

- Parse motion commands from the upper computer.
- Convert velocity commands to Ackermann steering and motor output.
- Maintain odometry using configured chassis parameters.
- Report chassis state to ROS 2 through the serial protocol.
- Provide emergency stop and safe stop behavior through the control chain.

## License

This project is licensed under the Apache License 2.0. See the repository-level [LICENSE](../LICENSE).
