# RDK X5 + LD14P 激光雷达 + 阿克曼底盘 SLAM 建图系统配置

## 📋 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        RDK X5 (ROS2)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ SLAM 建图    │  │ 导航控制     │  │ 激光雷达     │     │
│  │ (Cartographer│  │ (Nav2)       │  │ (LD14P)      │     │
│  │  /SLAM Toolbox)│  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            │                                │
│                   ┌────────▼────────┐                       │
│                   │  底盘控制节点   │                       │
│                   │ (base_controller)│                      │
│                   └────────┬────────┘                       │
│                            │                                │
│                   ┌────────▼────────┐                       │
│                   │  串口通信节点   │                       │
│                   │ (serial_node)   │                       │
│                   └────────┬────────┘                       │
└────────────────────────────┼────────────────────────────────┘
                             │ USB转TTL
                             │ (9600 baud)
┌────────────────────────────▼────────────────────────────────┐
│                      STM32F103RB                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ 串口接收     │  │ 阿克曼控制   │  │ 里程计计算   │     │
│  │ (USART1)     │  │ (舵机+电机)  │  │ (编码器)     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## 一、STM32 端参数配置

### 1.1 底盘物理参数（需要测量）

```c
// 在 STM32 代码中定义这些参数
// 建议创建文件: USER/ChassisParams.h

#ifndef _CHASSIS_PARAMS_H_
#define _CHASSIS_PARAMS_H_

// ========== 底盘几何参数 ==========
#define WHEELBASE           0.200f    // 轴距 (m) - 前后轮中心距离
#define TRACK_WIDTH         0.150f    // 轮距 (m) - 左右轮中心距离
#define WHEEL_DIAMETER      0.065f    // 轮子直径 (m)
#define WHEEL_RADIUS        (WHEEL_DIAMETER / 2.0f)

// ========== 转向参数 ==========
#define MAX_STEERING_ANGLE  0.524f    // 最大转向角 (rad) ≈ 30度
#define MIN_TURNING_RADIUS  0.400f    // 最小转弯半径 (m)

// ========== 速度限制 ==========
#define MAX_LINEAR_SPEED    1.0f      // 最大线速度 (m/s)
#define MAX_ANGULAR_SPEED   1.57f     // 最大角速度 (rad/s) ≈ 90度/秒

// ========== 电机参数 ==========
#define ENCODER_PPR         390       // 编码器每转脉冲数
#define GEAR_RATIO          30.0f     // 减速比
#define MOTOR_MAX_RPM       200       // 电机最大转速 (RPM)

// ========== 舵机参数 ==========
#define SERVO_CENTER_ANGLE  1500      // 舵机中位脉宽 (us)
#define SERVO_LEFT_MAX      1000      // 舵机左极限 (us)
#define SERVO_RIGHT_MAX     2000      // 舵机右极限 (us)
#define SERVO_ANGLE_RANGE   90.0f     // 舵机角度范围 (度)

#endif
```

### 1.2 串口通信协议设计

#### 1.2.1 RDK → STM32 控制命令

```c
// 命令格式: 帧头 + 命令类型 + 数据 + 校验和 + 帧尾
// 总长度: 10 字节

typedef struct {
    uint8_t  header[2];      // 帧头: 0xAA 0x55
    uint8_t  cmd_type;       // 命令类型
    int16_t  linear_vel;     // 线速度 (mm/s, -1000~1000)
    int16_t  angular_vel;    // 角速度 (mrad/s, -1570~1570)
    uint8_t  reserved;       // 保留字节
    uint8_t  checksum;       // 校验和
    uint8_t  tail;           // 帧尾: 0x0D
} __attribute__((packed)) ControlCmd_t;

// 命令类型定义
#define CMD_VELOCITY        0x01    // 速度控制
#define CMD_STOP            0x02    // 紧急停止
#define CMD_RESET           0x03    // 复位
#define CMD_GET_ODOM        0x04    // 请求里程计数据
#define CMD_SET_PARAM       0x05    // 设置参数
```

#### 1.2.2 STM32 → RDK 反馈数据

```c
// 里程计数据格式: 20 字节
typedef struct {
    uint8_t  header[2];      // 帧头: 0xBB 0x66
    uint8_t  data_type;      // 数据类型: 0x01=里程计
    int32_t  pos_x;          // X位置 (mm)
    int32_t  pos_y;          // Y位置 (mm)
    int16_t  yaw;            // 航向角 (mrad, -3140~3140)
    int16_t  linear_vel;     // 当前线速度 (mm/s)
    int16_t  angular_vel;    // 当前角速度 (mrad/s)
    uint8_t  checksum;       // 校验和
    uint8_t  tail;           // 帧尾: 0x0D
} __attribute__((packed)) OdomData_t;

// 状态数据格式: 12 字节
typedef struct {
    uint8_t  header[2];      // 帧头: 0xBB 0x66
    uint8_t  data_type;      // 数据类型: 0x02=状态
    uint8_t  battery_level;  // 电池电量 (0-100%)
    int16_t  motor_current;  // 电机电流 (mA)
    uint16_t error_code;     // 错误代码
    uint8_t  status;         // 状态标志位
    uint8_t  checksum;       // 校验和
    uint8_t  tail;           // 帧尾: 0x0D
} __attribute__((packed)) StatusData_t;
```

### 1.3 STM32 代码实现要点

#### 1.3.1 速度控制转换

```c
// 将 ROS2 的 cmd_vel (m/s, rad/s) 转换为阿克曼控制参数
void ConvertCmdVelToAckermann(float linear_vel, float angular_vel)
{
    // 计算转向角度 (阿克曼几何)
    float steering_angle = 0.0f;
    if (fabs(linear_vel) > 0.01f) {
        // steering_angle = atan(angular_vel * wheelbase / linear_vel)
        steering_angle = atan2f(angular_vel * WHEELBASE, linear_vel);
        
        // 限制转向角度
        if (steering_angle > MAX_STEERING_ANGLE)
            steering_angle = MAX_STEERING_ANGLE;
        if (steering_angle < -MAX_STEERING_ANGLE)
            steering_angle = -MAX_STEERING_ANGLE;
    }
    
    // 转换为舵机脉宽
    uint16_t servo_pulse = SteeringAngleToServoPulse(steering_angle);
    
    // 转换为电机速度 (-100 ~ 100)
    int8_t motor_speed = LinearVelToMotorSpeed(linear_vel);
    
    // 执行控制
    AckermannTurn(motor_speed, servo_pulse);
}

// 转向角度转舵机脉宽
uint16_t SteeringAngleToServoPulse(float angle_rad)
{
    // angle_rad: -MAX_STEERING_ANGLE ~ MAX_STEERING_ANGLE
    // 映射到 SERVO_LEFT_MAX ~ SERVO_RIGHT_MAX
    float normalized = angle_rad / MAX_STEERING_ANGLE;  // -1.0 ~ 1.0
    uint16_t pulse = SERVO_CENTER_ANGLE + 
                     (int16_t)(normalized * (SERVO_RIGHT_MAX - SERVO_CENTER_ANGLE));
    return pulse;
}

// 线速度转电机速度
int8_t LinearVelToMotorSpeed(float vel_ms)
{
    // vel_ms: -MAX_LINEAR_SPEED ~ MAX_LINEAR_SPEED
    // 映射到 -100 ~ 100
    int8_t speed = (int8_t)((vel_ms / MAX_LINEAR_SPEED) * 100.0f);
    if (speed > 100) speed = 100;
    if (speed < -100) speed = -100;
    return speed;
}
```



#### 1.3.2 里程计计算

```c
// 在定时器中断中定期调用 (如 10ms)
void Odometry_Update(void)
{
    // 获取编码器增量
    int32 delta_left = encoder_left - encoder_left_last;
    int32 delta_right = encoder_right - encoder_right_last;
    
    // 计算轮子转动距离
    float dist_left = (delta_left / (ENCODER_PPR * GEAR_RATIO)) * 
                      (2 * PI * WHEEL_RADIUS);
    float dist_right = (delta_right / (ENCODER_PPR * GEAR_RATIO)) * 
                       (2 * PI * WHEEL_RADIUS);
    
    // 计算中心点移动距离和角度变化
    float dist_center = (dist_left + dist_right) / 2.0f;
    float delta_yaw = (dist_right - dist_left) / TRACK_WIDTH;
    
    // 更新位置
    yaw += delta_yaw;
    pos_x += dist_center * cos(yaw);
    pos_y += dist_center * sin(yaw);
}
```

### 1.4 STM32 代码文件清单

已创建的文件：

1. `USER/ChassisParams.h` - 底盘物理参数定义
2. `USER/ROS2Protocol.h` - ROS2 通信协议定义
3. `USER/ROS2Protocol.c` - ROS2 通信协议实现
4. `USER/Odometry.h` - 里程计接口
5. `USER/Odometry.c` - 里程计实现
6. `USER/main_ros2.c` - ROS2 通信主程序

修改的文件：

1. `USER/Usart.c` - 添加 ROS2 协议处理
2. `USER/include.h` - 添加新头文件引用

## 二、RDK ROS2 端参数配置

### 2.1 底盘参数 YAML 配置

创建文件: `config/ackermann_params.yaml`

```yaml
# 阿克曼底盘参数配置
ackermann_chassis:
  # 底盘几何参数 (与 STM32 保持一致)
  wheelbase: 0.200          # 轴距 (m)
  track_width: 0.150        # 轮距 (m)
  wheel_diameter: 0.065     # 轮子直径 (m)
  wheel_radius: 0.0325      # 轮子半径 (m)
  
  # 转向参数
  max_steering_angle: 0.524 # 最大转向角 (rad) ≈ 30度
  min_turning_radius: 0.400 # 最小转弯半径 (m)
  
  # 速度限制
  max_linear_speed: 1.0     # 最大线速度 (m/s)
  max_angular_speed: 1.57   # 最大角速度 (rad/s)
  max_linear_accel: 0.5     # 最大线加速度 (m/s²)
  max_angular_accel: 1.0    # 最大角加速度 (rad/s²)
  
  # 串口通信参数
  serial_port: "/dev/ttyUSB0"  # 串口设备
  baud_rate: 9600              # 波特率
  
  # 发布频率
  odom_publish_rate: 20.0   # 里程计发布频率 (Hz)
  cmd_timeout: 0.5          # 命令超时时间 (s)
  
  # 坐标系
  base_frame: "base_link"
  odom_frame: "odom"
```

### 2.2 ROS2 节点实现

#### 2.2.1 串口通信节点

创建文件: `src/ackermann_serial_node.py`

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import String
import serial
import struct
import time

class AckermannSerialNode(Node):
    def __init__(self):
        super().__init__('ackermann_serial_node')
        
        # 声明参数
        self.declare_parameters(
            namespace='',
            parameters=[
                ('serial_port', '/dev/ttyUSB0'),
                ('baud_rate', 9600),
                ('wheelbase', 0.200),
                ('max_linear_speed', 1.0),
                ('max_angular_speed', 1.57),
                ('odom_frame', 'odom'),
                ('base_frame', 'base_link'),
            ]
        )
        
        # 获取参数
        self.serial_port = self.get_parameter('serial_port').value
        self.baud_rate = self.get_parameter('baud_rate').value
        self.wheelbase = self.get_parameter('wheelbase').value
        self.max_linear_speed = self.get_parameter('max_linear_speed').value
        self.max_angular_speed = self.get_parameter('max_angular_speed').value
        self.odom_frame = self.get_parameter('odom_frame').value
        self.base_frame = self.get_parameter('base_frame').value
        
        # 打开串口
        try:
            self.serial = serial.Serial(
                port=self.serial_port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1
            )
            self.get_logger().info(f'Serial port {self.serial_port} opened')
        except Exception as e:
            self.get_logger().error(f'Failed to open serial port: {e}')
            return
        
        # 订阅速度命令
        self.cmd_vel_sub = self.create_subscription(
            Twist,
            'cmd_vel',
            self.cmd_vel_callback,
            10
        )
        
        # 发布里程计
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        
        # 定时器：读取串口数据
        self.create_timer(0.01, self.read_serial)  # 100Hz
        
        # 接收缓冲区
        self.rx_buffer = bytearray()
        
        self.get_logger().info('Ackermann Serial Node started')
    
    def cmd_vel_callback(self, msg):
        """处理速度命令"""
        linear_vel = msg.linear.x  # m/s
        angular_vel = msg.angular.z  # rad/s
        
        # 限制速度
        linear_vel = max(min(linear_vel, self.max_linear_speed), 
                        -self.max_linear_speed)
        angular_vel = max(min(angular_vel, self.max_angular_speed),
                         -self.max_angular_speed)
        
        # 发送控制命令
        self.send_velocity_cmd(linear_vel, angular_vel)
    
    def send_velocity_cmd(self, linear_vel, angular_vel):
        """发送速度控制命令到 STM32"""
        # 转换单位: m/s -> mm/s, rad/s -> mrad/s
        linear_vel_mm = int(linear_vel * 1000)
        angular_vel_mrad = int(angular_vel * 1000)
        
        # 构造数据包
        packet = bytearray()
        packet.append(0xAA)  # 帧头0
        packet.append(0x55)  # 帧头1
        packet.append(0x01)  # 命令类型: CMD_VELOCITY
        packet.extend(struct.pack('<h', linear_vel_mm))    # 线速度 (小端)
        packet.extend(struct.pack('<h', angular_vel_mrad)) # 角速度 (小端)
        packet.append(0x00)  # 保留字节
        
        # 计算校验和
        checksum = sum(packet[2:8]) & 0xFF
        packet.append(checksum)
        packet.append(0x0D)  # 帧尾
        
        # 发送
        try:
            self.serial.write(packet)
        except Exception as e:
            self.get_logger().error(f'Failed to send command: {e}')
    
    def read_serial(self):
        """读取串口数据"""
        try:
            if self.serial.in_waiting > 0:
                data = self.serial.read(self.serial.in_waiting)
                self.rx_buffer.extend(data)
                self.parse_serial_data()
        except Exception as e:
            self.get_logger().error(f'Failed to read serial: {e}')
    
    def parse_serial_data(self):
        """解析串口数据"""
        while len(self.rx_buffer) >= 20:  # 里程计数据包长度
            # 查找帧头
            if self.rx_buffer[0] == 0xBB and self.rx_buffer[1] == 0x66:
                data_type = self.rx_buffer[2]
                
                if data_type == 0x01:  # 里程计数据
                    if len(self.rx_buffer) >= 20:
                        self.parse_odom_data(self.rx_buffer[:20])
                        self.rx_buffer = self.rx_buffer[20:]
                    else:
                        break
                else:
                    self.rx_buffer.pop(0)
            else:
                self.rx_buffer.pop(0)
    
    def parse_odom_data(self, data):
        """解析里程计数据"""
        # 验证校验和
        checksum = sum(data[2:18]) & 0xFF
        if checksum != data[18]:
            self.get_logger().warn('Odom checksum error')
            return
        
        # 解析数据
        pos_x_mm = struct.unpack('<i', data[3:7])[0]
        pos_y_mm = struct.unpack('<i', data[7:11])[0]
        yaw_mrad = struct.unpack('<h', data[11:13])[0]
        linear_vel_mm = struct.unpack('<h', data[13:15])[0]
        angular_vel_mrad = struct.unpack('<h', data[15:17])[0]
        
        # 转换单位
        pos_x = pos_x_mm / 1000.0
        pos_y = pos_y_mm / 1000.0
        yaw = yaw_mrad / 1000.0
        linear_vel = linear_vel_mm / 1000.0
        angular_vel = angular_vel_mrad / 1000.0
        
        # 发布里程计
        self.publish_odom(pos_x, pos_y, yaw, linear_vel, angular_vel)
    
    def publish_odom(self, x, y, yaw, vx, vyaw):
        """发布里程计消息"""
        odom = Odometry()
        odom.header.stamp = self.get_clock().now().to_msg()
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame
        
        # 位置
        odom.pose.pose.position.x = x
        odom.pose.pose.position.y = y
        odom.pose.pose.position.z = 0.0
        
        # 姿态 (四元数)
        import math
        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = math.sin(yaw / 2.0)
        odom.pose.pose.orientation.w = math.cos(yaw / 2.0)
        
        # 速度
        odom.twist.twist.linear.x = vx
        odom.twist.twist.linear.y = 0.0
        odom.twist.twist.angular.z = vyaw
        
        self.odom_pub.publish(odom)

def main(args=None):
    rclpy.init(args=args)
    node = AckermannSerialNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### 2.3 LD14P 激光雷达配置

创建文件: `config/ld14p.yaml`

```yaml
# LD14P 激光雷达参数
ldlidar:
  serial_port: "/dev/ttyUSB1"  # 雷达串口
  baud_rate: 115200
  frame_id: "laser_link"
  
  # 扫描参数
  angle_min: -3.14159          # 最小角度 (rad)
  angle_max: 3.14159           # 最大角度 (rad)
  range_min: 0.02              # 最小距离 (m)
  range_max: 12.0              # 最大距离 (m)
  
  # 滤波参数
  filter_min_range: 0.05       # 过滤最小距离
  filter_max_range: 10.0       # 过滤最大距离
```

### 2.4 TF 坐标变换配置

创建文件: `launch/robot_state_publisher.launch.py`

```python
from launch import LaunchDescription
from launch_ros.actions import Node
import os
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    # URDF 文件路径
    urdf_file = os.path.join(
        get_package_share_directory('ackermann_robot'),
        'urdf',
        'ackermann_robot.urdf'
    )
    
    with open(urdf_file, 'r') as f:
        robot_desc = f.read()
    
    return LaunchDescription([
        # Robot State Publisher
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_desc}]
        ),
    ])
```

### 2.5 URDF 机器人模型

创建文件: `urdf/ackermann_robot.urdf`

```xml
<?xml version="1.0"?>
<robot name="ackermann_robot">
  
  <!-- Base Link -->
  <link name="base_link">
    <visual>
      <geometry>
        <box size="0.25 0.15 0.10"/>
      </geometry>
      <material name="blue">
        <color rgba="0 0 0.8 1"/>
      </material>
    </visual>
  </link>
  
  <!-- Laser Link -->
  <link name="laser_link">
    <visual>
      <geometry>
        <cylinder radius="0.03" length="0.04"/>
      </geometry>
      <material name="black">
        <color rgba="0 0 0 1"/>
      </material>
    </visual>
  </link>
  
  <!-- Laser Joint -->
  <joint name="laser_joint" type="fixed">
    <parent link="base_link"/>
    <child link="laser_link"/>
    <origin xyz="0.10 0 0.08" rpy="0 0 0"/>
  </joint>
  
</robot>
```

### 2.6 Nav2 导航配置

创建文件: `config/nav2_params.yaml`

```yaml
# Nav2 参数配置 (针对阿克曼底盘)
bt_navigator:
  ros__parameters:
    use_sim_time: False
    global_frame: map
    robot_base_frame: base_link
    
controller_server:
  ros__parameters:
    use_sim_time: False
    controller_frequency: 20.0
    
    # Ackermann Controller
    FollowPath:
      plugin: "nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController"
      desired_linear_vel: 0.5
      max_linear_accel: 0.5
      max_linear_decel: 0.5
      lookahead_dist: 0.6
      min_lookahead_dist: 0.3
      max_lookahead_dist: 0.9
      use_velocity_scaled_lookahead_dist: true
      min_approach_linear_velocity: 0.05
      use_collision_detection: true
      max_allowed_time_to_collision_up_to_carrot: 1.0
      use_regulated_linear_velocity_scaling: true
      regulated_linear_scaling_min_radius: 0.4
      regulated_linear_scaling_min_speed: 0.25
      use_rotate_to_heading: false  # 阿克曼底盘不能原地旋转
      
local_costmap:
  local_costmap:
    ros__parameters:
      update_frequency: 5.0
      publish_frequency: 2.0
      global_frame: odom
      robot_base_frame: base_link
      rolling_window: true
      width: 3
      height: 3
      resolution: 0.05
      
global_costmap:
  global_costmap:
    ros__parameters:
      update_frequency: 1.0
      publish_frequency: 1.0
      global_frame: map
      robot_base_frame: base_link
      resolution: 0.05
```



### 2.7 SLAM 建图配置

#### 2.7.1 Cartographer SLAM

创建文件: `config/cartographer.lua`

```lua
include "map_builder.lua"
include "trajectory_builder.lua"

options = {
  map_builder = MAP_BUILDER,
  trajectory_builder = TRAJECTORY_BUILDER,
  map_frame = "map",
  tracking_frame = "base_link",
  published_frame = "odom",
  odom_frame = "odom",
  provide_odom_frame = false,  -- 使用外部里程计
  publish_frame_projected_to_2d = true,
  use_odometry = true,
  use_nav_sat = false,
  use_landmarks = false,
  num_laser_scans = 1,
  num_multi_echo_laser_scans = 0,
  num_subdivisions_per_laser_scan = 1,
  num_point_clouds = 0,
  lookup_transform_timeout_sec = 0.2,
  submap_publish_period_sec = 0.3,
  pose_publish_period_sec = 5e-3,
  trajectory_publish_period_sec = 30e-3,
  rangefinder_sampling_ratio = 1.,
  odometry_sampling_ratio = 1.,
  fixed_frame_pose_sampling_ratio = 1.,
  imu_sampling_ratio = 1.,
  landmarks_sampling_ratio = 1.,
}

-- 2D SLAM 配置
MAP_BUILDER.use_trajectory_builder_2d = true

TRAJECTORY_BUILDER_2D.min_range = 0.1
TRAJECTORY_BUILDER_2D.max_range = 10.0
TRAJECTORY_BUILDER_2D.missing_data_ray_length = 5.0
TRAJECTORY_BUILDER_2D.use_imu_data = false
TRAJECTORY_BUILDER_2D.use_online_correlative_scan_matching = true
TRAJECTORY_BUILDER_2D.motion_filter.max_angle_radians = math.rad(0.5)

-- 针对阿克曼底盘的优化
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 10
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.rotation_weight = 40

POSE_GRAPH.optimization_problem.huber_scale = 1e2
POSE_GRAPH.optimize_every_n_nodes = 35
POSE_GRAPH.constraint_builder.min_score = 0.65

return options
```

#### 2.7.2 SLAM Toolbox (替代方案)

创建文件: `config/slam_toolbox.yaml`

```yaml
slam_toolbox:
  ros__parameters:
    # 基本参数
    odom_frame: odom
    map_frame: map
    base_frame: base_link
    scan_topic: /scan
    use_map_saver: true
    mode: mapping  # mapping 或 localization
    
    # 扫描匹配参数
    resolution: 0.05
    max_laser_range: 10.0
    minimum_travel_distance: 0.2
    minimum_travel_heading: 0.2
    scan_buffer_size: 10
    scan_buffer_maximum_scan_distance: 10.0
    
    # 针对阿克曼底盘优化
    link_match_minimum_response_fine: 0.1
    link_scan_maximum_distance: 1.5
    loop_search_maximum_distance: 3.0
    do_loop_closing: true
    loop_match_minimum_chain_size: 10
    loop_match_maximum_variance_coarse: 3.0
    loop_match_minimum_response_coarse: 0.35
    loop_match_minimum_response_fine: 0.45
    
    # 相关性搜索空间
    correlation_search_space_dimension: 0.5
    correlation_search_space_resolution: 0.01
    correlation_search_space_smear_deviation: 0.1
    
    # 优化参数
    optimization_algorithm: "LevenbergMarquardt"
    max_iterations: 5
    transform_publish_period: 0.02
```

### 2.8 Launch 文件

#### 2.8.1 完整系统启动

创建文件: `launch/ackermann_slam.launch.py`

```python
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch.launch_description_sources import PythonLaunchDescriptionSource
import os
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    # 包路径
    pkg_dir = get_package_share_directory('ackermann_robot')
    
    # 参数文件
    ackermann_params = os.path.join(pkg_dir, 'config', 'ackermann_params.yaml')
    ld14p_params = os.path.join(pkg_dir, 'config', 'ld14p.yaml')
    slam_params = os.path.join(pkg_dir, 'config', 'slam_toolbox.yaml')
    
    return LaunchDescription([
        # 1. 串口通信节点
        Node(
            package='ackermann_robot',
            executable='ackermann_serial_node.py',
            name='ackermann_serial_node',
            output='screen',
            parameters=[ackermann_params]
        ),
        
        # 2. LD14P 激光雷达驱动
        Node(
            package='ldlidar_stl_ros2',
            executable='ldlidar_stl_ros2_node',
            name='ldlidar_publisher',
            output='screen',
            parameters=[ld14p_params]
        ),
        
        # 3. Robot State Publisher
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{
                'robot_description': open(os.path.join(
                    pkg_dir, 'urdf', 'ackermann_robot.urdf'
                )).read()
            }]
        ),
        
        # 4. SLAM Toolbox
        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[slam_params]
        ),
        
        # 5. RViz2 可视化
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', os.path.join(pkg_dir, 'rviz', 'slam.rviz')]
        ),
    ])
```

## 三、测试与调试

### 3.1 STM32 端测试

#### 3.1.1 编译选项

在 Keil 项目中添加宏定义：

```c
// 使用 ROS2 协议
#define USE_ROS2_PROTOCOL

// 或者使用简单串口控制
// #undef USE_ROS2_PROTOCOL
```

#### 3.1.2 测试步骤

1. 编译并下载程序到 STM32
2. 连接 USB 转 TTL 到电脑
3. 打开串口助手，波特率 9600
4. 观察初始化信息

预期输出：
```
=== ROS2 Ackermann Chassis Control ===
Wheelbase: 0.200 m
Track Width: 0.150 m
Wheel Diameter: 0.065 m
Max Linear Speed: 1.00 m/s
Max Angular Speed: 1.57 rad/s
Waiting for ROS2 commands...
```

#### 3.1.3 手动测试命令

使用串口助手发送十六进制数据：

```
前进 0.5 m/s:
AA 55 01 F4 01 00 00 00 F5 0D
解释: 帧头(AA 55) + 命令(01) + 线速度(500mm/s) + 角速度(0) + 保留(00) + 校验和(F5) + 帧尾(0D)

停止:
AA 55 02 00 00 00 00 00 02 0D
```

### 3.2 ROS2 端测试

#### 3.2.1 安装依赖

```bash
# 在 RDK X5 上执行
sudo apt update
sudo apt install -y \
    ros-humble-navigation2 \
    ros-humble-nav2-bringup \
    ros-humble-slam-toolbox \
    ros-humble-robot-state-publisher \
    python3-serial

# 安装 LD14P 驱动
cd ~/ros2_ws/src
git clone https://github.com/ldrobotSensorTeam/ldlidar_stl_ros2.git
cd ~/ros2_ws
colcon build --packages-select ldlidar_stl_ros2
```

#### 3.2.2 测试串口通信

```bash
# 1. 检查串口设备
ls -l /dev/ttyUSB*

# 2. 给串口权限
sudo chmod 666 /dev/ttyUSB0

# 3. 测试串口通信节点
ros2 run ackermann_robot ackermann_serial_node.py

# 4. 发送测试命令
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.3, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

# 5. 查看里程计数据
ros2 topic echo /odom
```

#### 3.2.3 测试激光雷达

```bash
# 1. 启动激光雷达
ros2 launch ldlidar_stl_ros2 ld14p.launch.py

# 2. 查看扫描数据
ros2 topic echo /scan

# 3. 在 RViz2 中可视化
rviz2
# 添加 LaserScan 显示，Topic 选择 /scan
```

### 3.3 完整系统测试

#### 3.3.1 启动完整系统

```bash
# 终端1: 启动所有节点
ros2 launch ackermann_robot ackermann_slam.launch.py

# 终端2: 键盘控制 (可选)
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

#### 3.3.2 建图测试

1. 启动系统后，在 RViz2 中应该能看到：
   - 激光雷达扫描点
   - 机器人模型
   - 正在构建的地图

2. 使用键盘控制小车移动：
   - `i`: 前进
   - `,`: 后退
   - `j`: 左转
   - `l`: 右转
   - `k`: 停止

3. 保存地图：
```bash
ros2 run nav2_map_server map_saver_cli -f ~/my_map
```

### 3.4 常见问题排查

#### 3.4.1 串口通信问题

```bash
# 问题: 无法打开串口
# 解决:
sudo chmod 666 /dev/ttyUSB0
# 或永久解决:
sudo usermod -a -G dialout $USER
# 然后重新登录

# 问题: 数据乱码
# 检查波特率是否匹配 (9600)
# 检查 STM32 和 RDK 的字节序是否一致
```

#### 3.4.2 里程计漂移

```python
# 问题: 里程计累积误差大
# 解决: 调整编码器参数
# 在 ChassisParams.h 中修改:
#define ENCODER_PPR         390       # 实际测量值
#define GEAR_RATIO          30.0f     # 实际减速比
#define WHEEL_DIAMETER      0.065f    # 实际测量轮径
```

#### 3.4.3 SLAM 建图质量差

```yaml
# 问题: 地图扭曲或不准确
# 解决: 调整 SLAM 参数
# 在 slam_toolbox.yaml 中:
minimum_travel_distance: 0.1  # 减小以提高精度
minimum_travel_heading: 0.1   # 减小以提高精度
resolution: 0.03              # 提高分辨率
```

## 四、参数测量指南

### 4.1 底盘几何参数测量

#### 轴距 (Wheelbase)
```
测量方法: 用卷尺测量前轮中心到后轮中心的距离
单位: 米 (m)
精度要求: ±5mm
```

#### 轮距 (Track Width)
```
测量方法: 测量左右轮中心的距离
单位: 米 (m)
精度要求: ±5mm
```

#### 轮子直径 (Wheel Diameter)
```
测量方法: 
1. 用卡尺测量轮子直径
2. 或者让轮子滚动一圈，测量行进距离，除以 π
单位: 米 (m)
精度要求: ±2mm
```

### 4.2 舵机角度校准

```c
// 测试程序
void CalibrateServo(void)
{
    // 1. 设置中位
    ServoSetPluseAndTime(0, 1500, 500);
    DelayMs(1000);
    // 观察舵机是否回正，如不正，调整 SERVO_CENTER_ANGLE
    
    // 2. 测试左极限
    ServoSetPluseAndTime(0, 1000, 500);
    DelayMs(1000);
    // 测量实际转向角度，调整 MAX_STEERING_ANGLE
    
    // 3. 测试右极限
    ServoSetPluseAndTime(0, 2000, 500);
    DelayMs(1000);
    // 测量实际转向角度
}
```

### 4.3 速度标定

```python
# ROS2 端测试脚本
import rclpy
from geometry_msgs.msg import Twist
import time

def test_speed():
    # 发送固定速度命令
    cmd = Twist()
    cmd.linear.x = 0.5  # 0.5 m/s
    
    # 发布 10 秒
    start_time = time.time()
    while time.time() - start_time < 10.0:
        pub.publish(cmd)
        time.sleep(0.1)
    
    # 测量实际行进距离
    # 实际速度 = 距离 / 10.0
    # 如果不匹配，调整 LinearVelToMotorSpeed() 函数
```

## 五、总结

### 5.1 关键参数清单

| 参数 | STM32 定义 | ROS2 配置 | 测量方法 |
|------|-----------|-----------|----------|
| 轴距 | WHEELBASE | wheelbase | 卷尺测量 |
| 轮距 | TRACK_WIDTH | track_width | 卷尺测量 |
| 轮径 | WHEEL_DIAMETER | wheel_diameter | 卡尺/滚动测量 |
| 最大转向角 | MAX_STEERING_ANGLE | max_steering_angle | 量角器测量 |
| 最大线速度 | MAX_LINEAR_SPEED | max_linear_speed | 实测标定 |
| 编码器 PPR | ENCODER_PPR | - | 查阅规格书 |
| 减速比 | GEAR_RATIO | - | 查阅规格书 |

### 5.2 通信协议总结

**RDK → STM32 (控制命令)**
- 帧头: 0xAA 0x55
- 长度: 10 字节
- 频率: 根据 cmd_vel 更新

**STM32 → RDK (里程计数据)**
- 帧头: 0xBB 0x66
- 长度: 20 字节
- 频率: 20 Hz (推荐)

### 5.3 下一步工作

1. ✅ 完成 STM32 代码实现
2. ✅ 完成 ROS2 节点实现
3. ⬜ 测量底盘物理参数
4. ⬜ 校准舵机和电机
5. ⬜ 测试串口通信
6. ⬜ 集成激光雷达
7. ⬜ 测试 SLAM 建图
8. ⬜ 配置导航系统

---

**文档版本**: v1.0  
**最后更新**: 2026-04-07  
**作者**: Kiro AI Assistant
