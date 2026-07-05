#!/usr/bin/env python3
"""
仅定位（map_server + AMCL + lifecycle_manager）
=========================================
适用场景：
  * 不跑路径规划，只想验证“地图加载 + AMCL 在 /scan_filtered 上能否定位”。
  * 排查 Nav2 启动失败时，先单独把定位栈拉起来缩小问题范围。

启动命令：
  ros2 launch czybot_navigation2 localization.launch.py
  ros2 launch czybot_navigation2 localization.launch.py \
      map:=/home/kkk/rdks100_slam/my_map/my_map.yaml
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    czybot_nav_dir = get_package_share_directory('czybot_navigation2')

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('use_rviz')
    map_yaml = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')

    default_map = os.path.join(
        os.path.expanduser('~'), 'rdks100_slam', 'my_map', 'my_map.yaml'
    )
    default_params = os.path.join(czybot_nav_dir, 'config', 'nav2_params.yaml')
    default_rviz = os.path.join(czybot_nav_dir, 'config', 'nav2_view.rviz')

    declared_arguments = [
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('use_rviz', default_value='true'),
        DeclareLaunchArgument('map', default_value=default_map),
        DeclareLaunchArgument('params_file', default_value=default_params),
    ]

    map_server = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        output='screen',
        parameters=[
            params_file,
            {
                'use_sim_time': use_sim_time,
                'yaml_filename': map_yaml,
            },
        ],
    )

    amcl = Node(
        package='nav2_amcl',
        executable='amcl',
        name='amcl',
        output='screen',
        parameters=[params_file, {'use_sim_time': use_sim_time}],
    )

    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_localization',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
            'autostart': True,
            'node_names': ['map_server', 'amcl'],
        }],
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', default_rviz],
        parameters=[{'use_sim_time': use_sim_time}],
        condition=IfCondition(use_rviz),
    )

    return LaunchDescription([
        *declared_arguments,
        LogInfo(msg='[czybot_navigation2] Localization-only stack starting.'),
        map_server,
        amcl,
        lifecycle_manager,
        rviz_node,
    ])
