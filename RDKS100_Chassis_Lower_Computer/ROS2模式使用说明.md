# STM32 ROS2模式使用说明

## 修改内容总结

### 1. STM32端修改

#### 修改的文件：
1. `USER/include.h` - 添加USE_ROS2_PROTOCOL宏定义和条件编译
2. `USER/main.c` - 根据宏定义选择初始化ROS2协议或简单串口控制
3. `USER/Usart.c` - 串口中断处理，根据模式调用不同的处理函数
4. `USER/Usart.h` - 添加Usart_SendByte函数声明
5. `USER/Odometry.c` - 添加ROS2格式的数据获取接口
6. `USER/ROS2Test.c` - 新建，实现ROS2定时器回调

#### 已存在的文件（无需修改）：
- `USER/ChassisParams.h` - 底盘物理参数定义
- `USER/ROS2Protocol.h/c` - ROS2通信协议实现
- `USER/Odometry.h` - 里程计接口定义
- `USER/AckermannControl.h/c` - 阿克曼底盘控制

### 2. 控制模式切换

#### 启用ROS2模式（当前状态）：
在 `USER/include.h` 中保留：
```c
#define USE_ROS2_PROTOCOL
```

#### 切换回简单串口控制：
在 `USER/include.h` 中注释掉：
```c
// #define USE_ROS2_PROTOCOL
```

## 编译和烧录

### 1. 在Keil中编译

1. 打开 `STM32_Motor.uvprojx` 或 `OpenArmSTM32.uvprojx`
2. 确保以下文件已添加到项目：
   - USER/ROS2Protocol.c
   - USER/Odometry.c
   - USER/ROS2Test.c
3. 点击 Build (F7) 编译
4. 应该看到 0 Error

### 2. 下载到STM32

1. 连接ST-Link到STM32
2. 点击 Download (F8)
3. 等待下载完成

### 3. 验证串口输出

打开串口助手（9600波特率），应该看到：
```
=== ROS2 Ackermann Chassis Control ===
Wheelbase: 0.200 m
Track Width: 0.150 m
Wheel Diameter: 0.065 m
Max Linear Speed: 1.00 m/s
Max Angular Speed: 1.57 rad/s
Waiting for ROS2 commands...
```

## ROS2上位机配置

### 1. 检查串口设备

在RDK上执行：
```bash
ls -l /dev/ttyUSB*
```

应该看到类似：
```
/dev/ttyUSB0  # STM32串口
/dev/ttyUSB1  # 激光雷达（如果有）
```

### 2. 设置串口权限

```bash
sudo chmod 666 /dev/ttyUSB0
```

或永久设置：
```bash
sudo usermod -a -G dialout $USER
# 然后重新登录
```

### 3. 修改stm32_bridge.py波特率

编辑 `chapt7_pro_ws/src/czybot_navigation2/scripts/stm32_bridge.py`

找到：
```python
self.declare_parameter('baudrate', 115200)
```

改为：
```python
self.declare_parameter('baudrate', 9600)
```

或者在启动时指定参数：
```bash
ros2 run czybot_navigation2 stm32_bridge.py --ros-args -p baudrate:=9600
```

## 测试步骤

### 测试1：STM32串口通信

在RDK上：
```bash
cd ~/chapt7_pro_ws
source install/setup.bash

# 启动STM32桥接节点
ros2 run czybot_navigation2 stm32_bridge.py --ros-args \
    -p port:=/dev/ttyUSB0 \
    -p baudrate:=9600
```

应该看到：
```
[INFO] [stm32_bridge]: 串口已打开: /dev/ttyUSB0 @ 9600
[INFO] [stm32_bridge]: STM32桥接节点已启动
```

### 测试2：发送速度命令

新开一个终端：
```bash
cd ~/chapt7_pro_ws
source install/setup.bash

# 发送前进命令（0.3 m/s）
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
    "{linear: {x: 0.3}, angular: {z: 0.0}}" --once

# 发送停止命令
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
    "{linear: {x: 0.0}, angular: {z: 0.0}}" --once
```

小车应该前进然后停止。

### 测试3：查看里程计数据

```bash
# 查看里程计话题
ros2 topic echo /odom
```

应该看到里程计数据更新（如果STM32正确发送）。

### 测试4：键盘控制

```bash
cd ~/chapt7_pro_ws
source install/setup.bash

# 启动键盘控制
ros2 run czybot_navigation2 ackermann_teleop_key.py
```

按键说明：
- `w` - 增加前进速度
- `s` - 减少速度
- `x` - 后退
- `a` - 左转
- `d` - 右转
- `空格` - 紧急停止
- `q` - 退出

## 完整系统启动

### 方法1：分步启动（推荐用于调试）

终端1 - STM32桥接：
```bash
cd ~/chapt7_pro_ws
source install/setup.bash
ros2 run czybot_navigation2 stm32_bridge.py --ros-args -p baudrate:=9600
```

终端2 - 激光雷达（如果有）：
```bash
cd ~/chapt7_pro_ws
source install/setup.bash
ros2 launch ldlidar_ros2 ld14p.launch.py
```

终端3 - 键盘控制：
```bash
cd ~/chapt7_pro_ws
source install/setup.bash
ros2 run czybot_navigation2 ackermann_teleop_key.py
```

### 方法2：使用launch文件（一键启动）

创建启动脚本 `chapt7_pro_ws/启动ROS2控制.sh`：
```bash
#!/bin/bash
cd ~/chapt7_pro_ws
source install/setup.bash

# 启动STM32桥接和键盘控制
ros2 launch czybot_navigation2 ackermann_control.launch.py
```

## 通信协议说明

### RDK → STM32 控制命令（10字节）

```
字节0-1: 帧头 0xAA 0x55
字节2:   命令类型 0x01=速度控制
字节3-4: 线速度 (int16, mm/s, 小端)
字节5-6: 角速度 (int16, mrad/s, 小端)
字节7:   保留 0x00
字节8:   校验和
字节9:   帧尾 0x0D
```

示例：前进0.5m/s
```
AA 55 01 F4 01 00 00 00 F5 0D
```

### STM32 → RDK 里程计数据（20字节）

```
字节0-1:   帧头 0xBB 0x66
字节2:     数据类型 0x01=里程计
字节3-6:   X位置 (int32, mm, 小端)
字节7-10:  Y位置 (int32, mm, 小端)
字节11-12: 航向角 (int16, mrad, 小端)
字节13-14: 线速度 (int16, mm/s, 小端)
字节15-16: 角速度 (int16, mrad/s, 小端)
字节17:    保留 0x00
字节18:    校验和
字节19:    帧尾 0x0D
```

## 常见问题

### 1. 小车不动

检查：
- STM32是否正确烧录了ROS2模式程序
- 串口连接是否正常
- stm32_bridge节点是否正常运行
- 使用 `ros2 topic echo /cmd_vel` 查看是否有命令发送

### 2. 串口打不开

```bash
# 检查设备
ls -l /dev/ttyUSB*

# 设置权限
sudo chmod 666 /dev/ttyUSB0

# 检查是否被占用
lsof /dev/ttyUSB0
```

### 3. 波特率不匹配

确保STM32和ROS2使用相同波特率：
- STM32: `Usart.c` 中 `USART_BaudRate = 9600`
- ROS2: stm32_bridge.py 参数 `baudrate:=9600`

### 4. 里程计数据不更新

检查：
- STM32是否定期发送里程计数据（每50ms）
- 使用串口助手查看STM32是否发送数据
- 检查校验和是否正确

### 5. 键盘控制无响应

- 确保终端窗口处于激活状态
- 检查是否有权限问题：`chmod +x ackermann_teleop_key.py`
- 查看节点是否运行：`ros2 node list`

## 参数调整

### 底盘物理参数

在 `USER/ChassisParams.h` 中修改：
```c
#define WHEELBASE           0.200f    // 轴距 (m)
#define TRACK_WIDTH         0.150f    // 轮距 (m)
#define WHEEL_DIAMETER      0.065f    // 轮径 (m)
#define MAX_STEERING_ANGLE  0.524f    // 最大转向角 (rad)
#define MAX_LINEAR_SPEED    1.0f      // 最大线速度 (m/s)
```

### 速度限制

在键盘控制中调整：
```bash
ros2 run czybot_navigation2 ackermann_teleop_key.py --ros-args \
    -p max_linear_vel:=0.8 \
    -p max_angular_vel:=1.5
```

## 下一步

1. ✅ STM32 ROS2模式已配置
2. ✅ ROS2桥接节点已就绪
3. ✅ 键盘控制已实现
4. ⬜ 测试实际硬件
5. ⬜ 校准底盘参数
6. ⬜ 集成激光雷达SLAM
7. ⬜ 实现自主导航

---

**文档版本**: v1.0  
**创建日期**: 2026-04-08  
**作者**: Kiro AI Assistant
