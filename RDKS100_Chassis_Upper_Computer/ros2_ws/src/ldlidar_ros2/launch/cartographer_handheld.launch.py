#!/usr/bin/env python3
"""
Cartographer手持雷达建图Launch文件
完全基于激光扫描匹配，不依赖里程计
适用于LD14P手持建图场景
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.conditions import IfCondition
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    
    # Cartographer配置文件路径
    cartographer_config_dir = PathJoinSubstitution([
        FindPackageShare('ldlidar'),
        'config'
    ])
    
    configuration_basename = 'cartographer_handheld.lua'
    
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
    
    port_name_arg = DeclareLaunchArgument(
        'port_name',
        default_value='/dev/ttyCH343USB0',
        description='LD14P serial port'
    )
    
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Whether to start RViz2'
    )
    
    resolution_arg = DeclareLaunchArgument(
        'resolution',
        default_value='0.05',
        description='Map resolution in meters'
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
    
    # 启动Cartographer节点
    cartographer_node = Node(
        package='cartographer_ros',
        executable='cartographer_node',
        name='cartographer_node',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        arguments=[
            '-configuration_directory', cartographer_config_dir,
            '-configuration_basename', configuration_basename,
        ],
        remappings=[
            ('scan', 'scan'),
            ('odom', 'odom'),  # 虽然不使用，但需要映射
        ]
    )
    
    # 启动Cartographer占用栅格节点（生成地图）
    cartographer_occupancy_grid_node = Node(
        package='cartographer_ros',
        executable='cartographer_occupancy_grid_node',
        name='cartographer_occupancy_grid_node',
        output='screen',
        parameters=[
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
            {'resolution': LaunchConfiguration('resolution')}
        ],
    )
    
    # 启动RViz2
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
    ld.add_action(resolution_arg)
    
    # 添加节点
    ld.add_action(ldlidar_launch)
    ld.add_action(cartographer_node)
    ld.add_action(cartographer_occupancy_grid_node)
    ld.add_action(rviz_node)
    
    return ld
