#!/usr/bin/env python3
"""
Hector SLAM建图Launch文件
使用Hector SLAM进行纯激光SLAM，不依赖里程计
专为手持激光雷达设计，轻量级，无需额外安装
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
        default_value='true',
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
    
    # 启动Hector Mapping节点
    hector_mapping_node = Node(
        package='hector_mapping',
        executable='hector_mapping',
        name='hector_mapping',
        output='screen',
        parameters=[
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
            # 坐标系配置
            {'map_frame': 'map'},
            {'base_frame': 'base_link'},
            {'odom_frame': 'base_link'},  # Hector不使用odom，直接map->base_link
            
            # 地图参数
            {'map_resolution': 0.05},  # 5cm分辨率
            {'map_size': 2048},  # 地图大小 2048*0.05 = 102.4米
            {'map_start_x': 0.5},
            {'map_start_y': 0.5},
            {'map_multi_res_levels': 2},
            
            # 更新参数 - 关键！降低阈值让手持建图更灵敏
            {'map_update_distance_thresh': 0.2},  # 移动20cm更新
            {'map_update_angle_thresh': 0.13},  # 旋转7.5度更新
            {'map_update_translational_thresh': 0.1},  # 平移10cm更新
            
            # 扫描匹配参数
            {'laser_min_dist': 0.1},  # LD14P最小距离
            {'laser_max_dist': 12.0},  # LD14P最大距离12米
            {'laser_z_min_value': -1.0},
            {'laser_z_max_value': 1.0},
            
            # TF发布
            {'pub_map_odom_transform': True},  # 发布map->odom变换
            {'pub_odometry': True},  # 发布里程计信息
            {'advertise_map_service': True},  # 提供地图服务
            
            # 扫描匹配器参数 - 优化手持建图
            {'scan_matcher_max_iterations': 5},  # 最大迭代次数
            
            # TF超时
            {'tf_map_scanmatch_transform_frame_name': 'scanmatcher_frame'},
            {'output_timing': False},
            
            # 更新频率
            {'map_pub_period': 1.0},  # 1Hz发布地图
        ],
        remappings=[
            ('scan', '/scan'),
        ]
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
    ld.add_action(hector_mapping_node)
    ld.add_action(rviz_node)
    
    return ld
