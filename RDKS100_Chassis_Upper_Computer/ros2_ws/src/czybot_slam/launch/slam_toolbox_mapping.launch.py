#!/usr/bin/env python3
"""
slam_toolbox 建图启动文件（备选方案）
硬件：RDK S100 + Livox Mid-360S + STM32底盘

相比Cartographer，slam_toolbox的优势：
  - CPU占用更低，适合RDK S100性能受限场景
  - 支持持久化地图（保存后可继续扩展）
  - 支持定位模式切换（无需重启）

用法：
  ros2 launch czybot_slam slam_toolbox_mapping.launch.py
  ros2 launch czybot_slam slam_toolbox_mapping.launch.py use_rviz:=false
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    czybot_slam_dir = get_package_share_directory('czybot_slam')
    livox_driver_dir = get_package_share_directory('livox_ros_driver2')

    # ─── 参数 ──────────────────────────────────────────────────
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='false',
        description='是否使用仿真时钟'
    )
    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz', default_value='true',
        description='是否启动RViz2'
    )
    declare_stm32_port = DeclareLaunchArgument(
        'stm32_port', default_value='/dev/ttyUSB0',
        description='STM32底盘串口'
    )
    declare_stm32_baudrate = DeclareLaunchArgument(
        'stm32_baudrate', default_value='115200',
        description='STM32波特率'
    )
    declare_slam_params = DeclareLaunchArgument(
        'slam_params_file',
        default_value=PathJoinSubstitution([
            FindPackageShare('czybot_slam'), 'config', 'slam_toolbox_params.yaml'
        ]),
        description='slam_toolbox参数文件路径'
    )

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('use_rviz')
    stm32_port = LaunchConfiguration('stm32_port')
    stm32_baudrate = LaunchConfiguration('stm32_baudrate')
    slam_params_file = LaunchConfiguration('slam_params_file')

    # ─── 1. STM32 底盘桥接 ─────────────────────────────────────
    stm32_bridge_node = Node(
        package='czybot_navigation2',
        executable='stm32_bridge',
        name='stm32_bridge',
        output='screen',
        parameters=[{
            'port': stm32_port,
            'baudrate': stm32_baudrate,
            'publish_tf': True,
        }]
    )

    # ─── 2. 静态TF：base_link → livox_frame ────────────────────
    # 雷达改为水平安装：仅保留安装高度，不再加入 pitch 旋转补偿。
    static_tf_base_to_livox = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_base_to_livox',
        arguments=[
            '0.0', '0.0', '0.15',              # 360S安装高度15cm
            '0.0', '0.0', '0.0', '1.0',        # qx qy qz qw：水平安装
            'base_link', 'livox_frame'
        ],
        output='screen'
    )

    # ─── 3. Livox Mid-360S 驱动 ────────────────────────────────
    livox_config_path = os.path.join(livox_driver_dir, 'config', 'MID360s_config.json')

    livox_driver_node = Node(
        package='livox_ros_driver2',
        executable='livox_ros_driver2_node',
        name='livox_lidar_publisher',
        output='screen',
        parameters=[{
            'xfer_format': 0,
            'multi_topic': 0,
            'data_src': 0,
            'publish_freq': 10.0,
            'output_data_type': 0,
            'frame_id': 'livox_frame',
            'use_sim_time': use_sim_time,
            'user_config_path': livox_config_path,
        }]
    )

    livox_delayed = TimerAction(period=3.0, actions=[livox_driver_node])

    # ─── 4. PointCloud2 → LaserScan ────────────────────────────
    pointcloud_to_laserscan_node = Node(
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='pointcloud_to_laserscan',
        output='screen',
        parameters=[
            os.path.join(czybot_slam_dir, 'config', 'pointcloud_to_laserscan.yaml'),
            {'use_sim_time': use_sim_time}
        ],
        remappings=[
            ('cloud_in', '/livox/lidar'),
            ('scan', '/scan'),
        ]
    )

    pc2scan_delayed = TimerAction(period=5.0, actions=[pointcloud_to_laserscan_node])

    # ─── 5. slam_toolbox 建图节点 ──────────────────────────────
    slam_toolbox_node = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[
            slam_params_file,
            {'use_sim_time': use_sim_time}
        ]
    )

    slam_delayed = TimerAction(period=7.0, actions=[slam_toolbox_node])

    # ─── 6. RViz2 ─────────────────────────────────────────────
    rviz_config = os.path.join(czybot_slam_dir, 'rviz', 'slam_2d.rviz')

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': use_sim_time}],
        condition=IfCondition(use_rviz)
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_use_rviz,
        declare_stm32_port,
        declare_stm32_baudrate,
        declare_slam_params,

        LogInfo(msg='[czybot_slam] 启动 slam_toolbox 建图（轻量备选方案）...'),
        LogInfo(msg='[czybot_slam] 建图完成后执行: ros2 run nav2_map_server map_saver_cli -f ~/rdks100_slam/my_map/my_map'),

        stm32_bridge_node,
        static_tf_base_to_livox,
        rviz_node,
        livox_delayed,
        pc2scan_delayed,
        slam_delayed,
    ])
