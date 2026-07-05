#!/usr/bin/env python3
"""
完整机器人启动文件（包含STM32、TJC串口屏）

重要配置：
- STM32串口：/dev/ttyUSB0，波特率115200
- TJC串口屏：/dev/ttyUSB1，波特率115200
- 两个设备必须使用相同的波特率115200

使用方法：
  ros2 launch czybot_navigation2 robot_with_hmi.launch.py
  
自定义参数：
  ros2 launch czybot_navigation2 robot_with_hmi.launch.py \
    stm32_port:=/dev/ttyUSB0 \
    tjc_port:=/dev/ttyUSB1
"""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_dir = get_package_share_directory('czybot_navigation2')
    
    # 声明启动参数
    stm32_port_arg = DeclareLaunchArgument(
        'stm32_port',
        default_value='/dev/ttyUSB0',
        description='STM32串口端口（波特率115200）'
    )
    
    tjc_port_arg = DeclareLaunchArgument(
        'tjc_port',
        default_value='/dev/ttyUSB1',
        description='TJC串口屏端口（波特率115200，必须与STM32一致）'
    )
    
    # STM32桥接节点
    stm32_bridge_node = Node(
        package='czybot_navigation2',
        executable='stm32_bridge',
        name='stm32_bridge',
        output='screen',
        parameters=[{
            'port': LaunchConfiguration('stm32_port'),
            'baudrate': 115200,  # STM32波特率：115200（固件已确认为115200）
            'publish_tf': True,
        }]
    )
    
    # TJC串口屏节点
    tjc_hmi_node = Node(
        package='czybot_navigation2',
        executable='tjc_hmi_bridge',
        name='tjc_hmi_bridge',
        output='screen',
        parameters=[{
            'port': LaunchConfiguration('tjc_port'),
            'baudrate': 115200,  # TJC波特率：115200
            'update_rate': 10.0,
        }]
    )
    
    # 激光雷达节点（如果需要）
    # ldlidar_launch = IncludeLaunchDescription(
    #     PythonLaunchDescriptionSource(
    #         os.path.join(
    #             get_package_share_directory('ldlidar_ros2'),
    #             'launch',
    #             'ld14p.launch.py'
    #         )
    #     )
    # )
    
    return LaunchDescription([
        stm32_port_arg,
        tjc_port_arg,
        stm32_bridge_node,
        tjc_hmi_node,
        # ldlidar_launch,  # 取消注释以启动激光雷达
    ])
