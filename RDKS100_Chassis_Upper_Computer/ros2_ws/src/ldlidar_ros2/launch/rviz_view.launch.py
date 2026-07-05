#!/usr/bin/env python3
"""
RViz2可视化Launch文件
在本地电脑上运行，连接到RDK的SLAM节点
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    
    # RViz配置文件路径
    rviz_config_file = PathJoinSubstitution([
        FindPackageShare('ldlidar'),
        'rviz2',
        'slam_mapping.rviz'
    ])
    
    # 声明launch参数
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock if true'
    )
    
    # 启动RViz2可视化
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_file],
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}]
    )
    
    # 组装LaunchDescription
    ld = LaunchDescription()
    
    # 添加参数声明
    ld.add_action(use_sim_time_arg)
    
    # 添加节点
    ld.add_action(rviz_node)
    
    return ld
