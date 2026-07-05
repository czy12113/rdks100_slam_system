#!/usr/bin/env python3
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import glob
import re

'''
Parameter Description:
---
- Set laser scan directon: 
  1. Set counterclockwise, example: {'laser_scan_dir': True}
  2. Set clockwise,        example: {'laser_scan_dir': False}
- Angle crop setting, Mask data within the set angle range:
  1. Enable angle crop fuction:
    1.1. enable angle crop,  example: {'enable_angle_crop_func': True}
    1.2. disable angle crop, example: {'enable_angle_crop_func': False}
  2. Angle cropping interval setting:
  - The distance and intensity data within the set angle range will be set to 0.
  - angle >= 'angle_crop_min' and angle <= 'angle_crop_max' which is [angle_crop_min, angle_crop_max], unit is degress.
    example:
      {'angle_crop_min': 135.0}
      {'angle_crop_max': 225.0}
      which is [135.0, 225.0], angle unit is degress.
'''

def generate_launch_description():
  # 自动检测雷达串口设备（兼容 CH343USB / ACM / USB 多种名称）
  detected_ports = []
  try:
    # 检测多种常见的 USB 转串口设备名
    detected_ports = sorted(
        glob.glob('/dev/ttyCH343USB*') +
        glob.glob('/dev/ttyACM*') +
        glob.glob('/dev/ttyUSB*')
    )
  except Exception:
    detected_ports = []

  default_port = '/dev/ttyACM0'
  if detected_ports:
    # 过滤，只保留有效设备名
    valid = [p for p in detected_ports
             if re.match(r'^/dev/tty(CH343USB|ACM|USB)\d+$', p)]
    if valid:
      default_port = valid[0]

  # RDK x5 + CH343/CH9102 转串口时常见设备名；也可用 launch 参数覆盖，例如：
  # ros2 launch ldlidar ld14p.launch.py port_name:=/dev/ttyCH343USB0
  port_arg = DeclareLaunchArgument(
      'port_name',
      default_value=default_port,
      description='LD14P 串口设备路径（在板子上用 ls -l /dev/ttyCH343* 确认）',
  )
  # LDROBOT LiDAR publisher node
  ldlidar_node = Node(
      package='ldlidar',
      executable='ldlidar',
      name='ldlidar_publisher_ld14p',
      output='screen',
      parameters=[{
        'product_name': 'LDLiDAR_LD14P',
        'topic_name': 'scan',
        'port_name': LaunchConfiguration('port_name'),
        'frame_id': 'base_laser',
        'laser_scan_dir': True,
        'enable_angle_crop_func': False,
        'angle_crop_min': 135.0,
        'angle_crop_max': 225.0,
        'truncated_mode_': 0,
      }],
  )

  # base_link to base_laser tf node
  base_link_to_laser_tf_node = Node(
    package='tf2_ros',
    executable='static_transform_publisher',
    name='base_link_to_base_laser_ld14p',
    arguments=['0','0','0.18','0','0','0','base_link','base_laser']
  )

  scan_fre_node = ExecuteProcess(
    cmd=['ros2','run','ldlidar','LD14P_scan_fre.py']
  )


  # Define LaunchDescription variable
  ld = LaunchDescription()
  ld.add_action(port_arg)
  #ld.add_action(scan_fre_node)  #<!--调节雷达扫描频率，scan_fre扫描频率与雷达串口号请在LD14P_scan_fre.py文件中修改-->
  ld.add_action(ldlidar_node)
  ld.add_action(base_link_to_laser_tf_node)

  return ld