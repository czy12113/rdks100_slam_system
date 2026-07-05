#!/usr/bin/env python3
"""
SLAM建图Launch文件
整合LD14P雷达驱动、slam_toolbox在线建图和RViz2可视化
适用于手持雷达建图场景
一条命令启动所有功能
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.conditions import IfCondition
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.launch_description_sources import PythonLaunchDescriptionSource
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    
    # 获取包路径
    ldlidar_dir = get_package_share_directory('ldlidar')
    
    # Cartographer配置文件路径
    slam_params_file = PathJoinSubstitution([
        FindPackageShare('ldlidar'),
        'config',
        'handheld_mapper.yaml'  # 使用手持雷达专用配置
    ])
    
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
        description='Use simulation (Gazebo) clock if true'
    )
    
    port_name_arg = DeclareLaunchArgument(
        'port_name',
        default_value='/dev/ttyCH343USB0',
        description='LD14P serial port'
    )
    
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',  # 默认启动RViz2（使用ssh -X可以看到）
        description='Whether to start RViz2'
    )
    
    # 启动LD14P雷达驱动
    ldlidar_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ldlidar'),
                'launch',
                'ld14p.launch.py'
            ])
        ]),
        launch_arguments={
            'port_name': LaunchConfiguration('port_name')
        }.items()
    )
    
    # 不再需要odom到base_link的静态变换！
    # slam_toolbox会直接发布map->base_link
    
    # 启动slam_toolbox异步建图节点
    slam_toolbox_node = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[
            slam_params_file,
            {'use_sim_time': LaunchConfiguration('use_sim_time')}
        ],
    )
    
    # 启动RViz2可视化
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_file],
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        condition=IfCondition(LaunchConfiguration('use_rviz'))
    )
    
    # 组装LaunchDescription
    ld = LaunchDescription()
    
    # 添加参数声明
    ld.add_action(use_sim_time_arg)
    ld.add_action(port_name_arg)
    ld.add_action(use_rviz_arg)
    
    # 添加节点
    ld.add_action(ldlidar_launch)
    ld.add_action(slam_toolbox_node)
    ld.add_action(rviz_node)
    
    return ld
