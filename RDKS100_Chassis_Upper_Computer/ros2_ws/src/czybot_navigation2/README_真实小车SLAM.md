# 真实小车SLAM建图完整指南

## 系统架构

### 硬件组成
- **上位机**: 地瓜机器人 RDK S100 (运行 ROS2 Humble)
- **激光雷达**: Livox Mid-360S
- **下位机**: STM32F103 + 驱动模块
- **通信**: STM32通过串口与RDK S100通信

### 软件架构
```
ROS2 (RDK S100)
├── 键盘控制节点 (teleop_key)
│   └── 发布 /cmd_vel
├── STM32桥接节点 (stm32_bridge)
│   ├── 订阅 /cmd_vel → 发送控制命令到STM32
│   └── 接收STM32里程计 → 发布 /odom 和 TF
├── 雷达驱动节点 (ldlidar)
│   └── 发布 /scan
└── SLAM建图节点 (slam_toolbox)
    └── 订阅 /scan 和 /odom → 生成地图

STM32 (下位机)
├── 接收控制命令 (0xAA 0x55 ...)
├── 控制电机运动
├── 计算里程计
└── 发送里程计数据 (0xBB 0x66 ...)
```

## 通信协议

### RDK → STM32 控制命令 (10字节)
```
帧头: 0xAA 0x55
命令类型: 0x01 (速度控制)
线速度: int16 (mm/s, -1000~1000)
角速度: int16 (mrad/s, -1570~1570)
保留: 0x00
校验和: uint8 (从cmd_type到reserved的和)
帧尾: 0x0D
```

### STM32 → RDK 里程计数据 (20字节)
```
帧头: 0xBB 0x66
数据类型: 0x01 (里程计)
X位置: int32 (mm)
Y位置: int32 (mm)
航向角: int16 (mrad, -3140~3140)
线速度: int16 (mm/s)
角速度: int16 (mrad/s)
校验和: uint8
帧尾: 0x0D
```

## 安装步骤

### 1. 检查硬件连接

```bash
# 查看串口设备
ls -l /dev/tty*

# 常见设备名：
# LD14P雷达: /dev/ttyCH343USB0 或 /dev/ttyCH343USB1
# STM32: /dev/ttyUSB0 或 /dev/ttyUSB1 或 /dev/ttyACM0

# 设置串口权限
sudo chmod 666 /dev/ttyUSB0
sudo chmod 666 /dev/ttyCH343USB0

# 永久解决权限问题
sudo usermod -aG dialout $USER
# 然后重新登录
```

### 2. 安装依赖

```bash
# 安装ROS2包
sudo apt update
sudo apt install -y \
    ros-humble-slam-toolbox \
    ros-humble-nav2-map-server \
    ros-humble-rviz2 \
    ros-humble-tf2-ros \
    ros-humble-tf2-tools

# 安装Python依赖
pip3 install pyserial
```

### 3. 编译项目

```bash
cd ~/chapt7_pro_ws
colcon build --packages-select czybot_navigation2
source install/setup.bash
```

## 使用方法

### 方式一：一键启动（推荐）

```bash
# 确保已source环境
source ~/chapt7_pro_ws/install/setup.bash

# 启动SLAM建图（会自动启动所有节点）
ros2 launch czybot_navigation2 slam_real_robot.launch.py

# 如果串口设备不同，可以指定：
ros2 launch czybot_navigation2 slam_real_robot.launch.py \
    lidar_port:=/dev/ttyCH343USB1 \
    stm32_port:=/dev/ttyUSB1
```

### 方式二：分步启动（调试用）

```bash
# 终端1: 启动雷达驱动
ros2 run ldlidar ldlidar --ros-args \
    -p port_name:=/dev/ttyCH343USB0 \
    -p product_name:=LDLiDAR_LD14P

# 终端2: 启动STM32桥接
ros2 run czybot_navigation2 stm32_bridge --ros-args \
    -p port:=/dev/ttyUSB0 \
    -p baudrate:=115200

# 终端3: 启动SLAM
ros2 launch czybot_navigation2 slam_ld14p.launch.py

# 终端4: 键盘控制（可选）
ros2 run czybot_navigation2 teleop_key
```

### 键盘控制说明

```
w - 前进
s - 后退
a - 左转
d - 右转
空格 - 停止
q - 退出
```

## 建图流程

### 1. 启动系统

```bash
ros2 launch czybot_navigation2 slam_real_robot.launch.py
```

启动后会自动打开RViz2，你应该能看到：
- 红色的激光扫描点云
- 机器人的坐标系
- 逐渐生成的灰色地图

### 2. 测试通信

在新终端中测试：

```bash
# 查看话题
ros2 topic list

# 应该看到：
# /scan - 激光数据
# /odom - 里程计数据
# /cmd_vel - 速度命令
# /map - 地图数据

# 查看雷达数据
ros2 topic hz /scan
# 应该显示约10Hz

# 查看里程计数据
ros2 topic echo /odom --once

# 测试速度命令
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
    "{linear: {x: 0.1}, angular: {z: 0.0}}" --once
# 小车应该前进
```

### 3. 开始建图

使用键盘控制小车移动：

1. **缓慢移动**: 速度不要太快，类似正常走路
2. **旋转扫描**: 让小车原地旋转，扫描周围环境
3. **沿边缘走**: 沿着房间边缘走一圈
4. **覆盖区域**: 确保新区域与已建图区域有重叠
5. **观察RViz**: 实时查看地图生成效果

### 4. 保存地图

建图完成后：

```bash
# 保存地图
ros2 run nav2_map_server map_saver_cli -f ~/my_map

# 会生成两个文件：
# my_map.pgm - 地图图像
# my_map.yaml - 地图配置
```

## 调试技巧

### 检查串口通信

```bash
# 查看STM32桥接节点日志
ros2 run czybot_navigation2 stm32_bridge --ros-args --log-level debug

# 监听串口数据（调试用）
sudo cat /dev/ttyUSB0
```

### 检查TF树

```bash
# 查看TF树
ros2 run tf2_tools view_frames

# 会生成frames.pdf，应该看到：
# map -> odom -> base_link -> base_laser

# 实时查看TF
ros2 run tf2_ros tf2_echo map base_link
```

### 检查话题频率

```bash
# 雷达数据频率（应该约10Hz）
ros2 topic hz /scan

# 里程计频率（取决于STM32发送频率）
ros2 topic hz /odom

# 地图更新频率
ros2 topic hz /map
```

### RViz2配置

如果RViz2中看不到数据：

1. **Fixed Frame**: 设置为 `map`
2. **LaserScan**:
   - Topic: `/scan`
   - Size: 0.05
   - Color: 红色
3. **Map**:
   - Topic: `/map`
   - Color Scheme: map
4. **TF**: 勾选显示所有坐标系

## 常见问题

### 1. 串口打不开

```bash
# 检查设备是否存在
ls -l /dev/ttyUSB*

# 检查权限
sudo chmod 666 /dev/ttyUSB0

# 检查是否被占用
sudo lsof /dev/ttyUSB0
```

### 2. 收不到里程计数据

- 检查STM32程序是否正确烧录
- 检查串口波特率是否匹配（115200）
- 使用串口调试工具查看原始数据
- 检查STM32是否正确发送里程计数据

### 3. 小车不动

- 检查 `/cmd_vel` 话题是否有数据
- 检查STM32桥接节点是否正常运行
- 检查电机驱动是否正常
- 检查电池电量

### 4. 地图质量差

调整SLAM参数 `config/slam_toolbox_params.yaml`:

```yaml
# 降低更新阈值
minimum_travel_distance: 0.05  # 移动5cm就更新
minimum_travel_heading: 0.05   # 旋转0.05弧度就更新

# 提高地图分辨率
resolution: 0.03  # 3cm分辨率（更精细）
```

### 5. 雷达位置不对

修改 `launch/slam_real_robot.launch.py` 中的TF：

```python
arguments=[
    '0.05',  # x: 雷达在底盘前方5cm
    '0.0',   # y: 左右居中
    '0.15',  # z: 雷达高度15cm
    '0', '0', '0',
    'base_link',
    'base_laser'
],
```

## STM32代码说明

你的STM32需要实现以下功能：

### 1. 接收控制命令

```c
// 在串口接收中断或主循环中调用
void ROS2Protocol_ProcessByte(uint8 data);

// 在ROS2Protocol.c中实现命令处理
void ProcessControlCmd(ControlCmd_t* cmd) {
    // 提取速度
    float linear_vel = cmd->linear_vel / 1000.0f;  // mm/s -> m/s
    float angular_vel = cmd->angular_vel / 1000.0f;  // mrad/s -> rad/s
    
    // 控制电机
    AckermannControl(linear_vel, angular_vel);
}
```

### 2. 发送里程计数据

```c
// 在定时器中定期调用（如50Hz）
void Timer_Callback(void) {
    // 更新里程计
    Odometry_Update();
    
    // 获取里程计数据
    Odometry_t odom;
    Odometry_GetData(&odom);
    
    // 转换单位并发送
    int32 pos_x = (int32)(odom.pos_x * 1000);  // m -> mm
    int32 pos_y = (int32)(odom.pos_y * 1000);
    int16 yaw = (int16)(odom.yaw * 1000);  // rad -> mrad
    int16 linear_vel = (int16)(odom.linear_vel * 1000);
    int16 angular_vel = (int16)(odom.angular_vel * 1000);
    
    ROS2Protocol_SendOdom(pos_x, pos_y, yaw, linear_vel, angular_vel);
}
```

## 参数调整

### 雷达参数

编辑 `launch/slam_real_robot.launch.py`:

```python
parameters=[{
    'product_name': 'LDLiDAR_LD14P',
    'port_name': '/dev/ttyCH343USB0',  # 串口设备
    'frame_id': 'base_laser',
    'laser_scan_dir': True,  # 扫描方向
}]
```

### STM32通信参数

```python
parameters=[{
    'port': '/dev/ttyUSB0',  # STM32串口
    'baudrate': 115200,  # 波特率
    'publish_tf': True,  # 是否发布TF
}]
```

### SLAM参数

编辑 `config/slam_toolbox_params.yaml`:

```yaml
# 关键参数
resolution: 0.05  # 地图分辨率（米）
max_laser_range: 12.0  # 雷达最大距离
minimum_travel_distance: 0.05  # 最小移动距离
minimum_travel_heading: 0.05  # 最小旋转角度
```

## 下一步

建图完成后，你可以：

1. **定位导航**: 使用生成的地图进行自主导航
2. **路径规划**: 集成Nav2进行路径规划
3. **避障**: 添加动态避障功能
4. **多传感器融合**: 添加IMU、摄像头等传感器

## 文件清理

以下文件已不再需要，可以删除：

- `scripts/fake_vel_odom.py` - 假的里程计（已被真实里程计替代）
- `scripts/simple_odom.py` - 简单里程计（已被STM32里程计替代）
- `launch/slam_no_odom.launch.py` - 无里程计模式（已不需要）
- `launch/slam_simple_odom.launch.py` - 简单里程计模式（已不需要）
- `launch/slam_with_scan_matcher.launch.py` - 激光匹配里程计（已不需要）
- `config/slam_toolbox_no_odom.yaml` - 无里程计配置（已不需要）

## 技术支持

如有问题，请检查：

1. 串口连接和权限
2. ROS2环境是否正确source
3. 节点日志输出
4. TF树是否完整
5. 话题数据是否正常

祝建图顺利！🚀
