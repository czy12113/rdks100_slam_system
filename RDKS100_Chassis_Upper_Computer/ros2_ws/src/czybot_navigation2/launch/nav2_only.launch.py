#!/usr/bin/env python3
"""
仅启动 Nav2（不启动雷达/底盘）
=========================================
适用场景：
  * 已经在另一个终端跑了 cartographer_2d_slam 的传感器链（雷达/转换/滤波）
    并希望直接套上 Nav2；
  * 想只调 Nav2 而不想反复重启雷达。

前置话题/TF（必须存在）：
  * TF: map(可选)→odom→base_link→livox_frame
        其中 odom→base_link 由 stm32_bridge 提供；map→odom 由 AMCL 提供。
  * /odom        nav_msgs/Odometry           （stm32_bridge 发布）
  * /scan_filtered sensor_msgs/LaserScan      （czybot_slam 滤波链发布）

启动命令：
  ros2 launch czybot_navigation2 nav2_only.launch.py
  ros2 launch czybot_navigation2 nav2_only.launch.py \
      map:=/home/kkk/rdks100_slam/my_map/my_map.yaml use_rviz:=false
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml


def generate_launch_description():
    czybot_nav_dir = get_package_share_directory('czybot_navigation2')
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('use_rviz')
    map_yaml = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')
    autostart = LaunchConfiguration('autostart')
    use_composition = LaunchConfiguration('use_composition')
    use_respawn = LaunchConfiguration('use_respawn')

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
        DeclareLaunchArgument('autostart', default_value='true'),
        DeclareLaunchArgument('use_composition', default_value='False'),
        DeclareLaunchArgument('use_respawn', default_value='False'),
    ]

    # 同 livox_navigation.launch.py：把 BT XML 路径注入参数副本
    bt_xml_nav_to_pose = os.path.join(
        czybot_nav_dir, 'behavior_trees', 'navigate_to_pose_ackermann.xml'
    )
    bt_xml_nav_through_poses = os.path.join(
        czybot_nav_dir, 'behavior_trees', 'navigate_through_poses_ackermann.xml'
    )
    configured_params = RewrittenYaml(
        source_file=params_file,
        root_key='',
        param_rewrites={
            'default_nav_to_pose_bt_xml': bt_xml_nav_to_pose,
            'default_nav_through_poses_bt_xml': bt_xml_nav_through_poses,
        },
        convert_types=True,
    )

    nav2_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')
        ),
        launch_arguments={
            'map': map_yaml,
            'use_sim_time': use_sim_time,
            'params_file': configured_params,
            'autostart': autostart,
            'use_composition': use_composition,
            'use_respawn': use_respawn,
        }.items(),
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
        LogInfo(msg='[czybot_navigation2] Bringing up Nav2 only.'),
        nav2_bringup,
        rviz_node,
    ])
