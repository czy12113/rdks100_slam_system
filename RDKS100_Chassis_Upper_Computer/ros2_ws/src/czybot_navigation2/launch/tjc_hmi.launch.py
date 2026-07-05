#!/usr/bin/env python3
"""
启动陶晶驰串口屏节点

重要配置：
- 默认串口：/dev/ttyUSB1
- 默认波特率：115200（与STM32保持一致）
- 需在TJC HMI软件中设置波特率为115200

使用方法：
  ros2 launch czybot_navigation2 tjc_hmi.launch.py
  
自定义参数：
  ros2 launch czybot_navigation2 tjc_hmi.launch.py port:=/dev/ttyUSB1 baudrate:=115200
"""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_dir = get_package_share_directory('czybot_navigation2')
    config_file = os.path.join(pkg_dir, 'config', 'tjc_hmi_params.yaml')
    
    # 声明启动参数
    port_arg = DeclareLaunchArgument(
        'port',
        default_value='/dev/ttyUSB1',
        description='TJC串口屏端口（STM32是/dev/ttyUSB0）'
    )
    
    baudrate_arg = DeclareLaunchArgument(
        'baudrate',
        default_value='115200',
        description='TJC串口屏波特率115200'
    )
    
    # TJC HMI节点
    tjc_hmi_node = Node(
        package='czybot_navigation2',
        executable='tjc_hmi_bridge',
        name='tjc_hmi_bridge',
        output='screen',
        parameters=[
            config_file,
            {
                'port': LaunchConfiguration('port'),
                'baudrate': LaunchConfiguration('baudrate'),
            }
        ],
        remappings=[
            # 如果需要重映射话题，在这里添加
        ]
    )
    
    return LaunchDescription([
        port_arg,
        baudrate_arg,
        tjc_hmi_node,
    ])
