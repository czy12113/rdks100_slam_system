#!/usr/bin/env python3
"""
Cartographer 3D SLAM 建图启动文件
硬件：RDK S100 + Livox Mid-360S + STM32底盘

数据流：
  Mid-360S ──→ /livox/lidar (PointCloud2)  ──→ cartographer_node (3D)
  Mid-360S ──→ /livox/imu  (Imu)            ──→ cartographer_node (3D)
  STM32    ──→ /odom                         ──→ cartographer_node (3D)

TF 树：
  map → odom (由Cartographer发布)
  odom → base_link (由STM32底盘发布)
  base_link → livox_frame (静态TF)

特点：
  - 生成真3D地图（.pbstream）
  - 同时通过cartographer_occupancy_grid_node输出2D投影地图
  - 利用360S内置IMU提升建图精度（可选）

用法：
  ros2 launch czybot_slam cartographer_3d_slam.launch.py
  ros2 launch czybot_slam cartographer_3d_slam.launch.py use_imu:=true
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    # ─── 包路径 ────────────────────────────────────────────────
    czybot_slam_dir = get_package_share_directory('czybot_slam')
    livox_driver_dir = get_package_share_directory('livox_ros_driver2')

    # ─── Launch 参数 ───────────────────────────────────────────
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
    declare_use_imu = DeclareLaunchArgument(
        'use_imu', default_value='false',
        description='是否使用360S内置IMU数据（true=更精确但需标定）'
    )
    declare_resolution = DeclareLaunchArgument(
        'resolution', default_value='0.05',
        description='2D投影地图分辨率(m)'
    )

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('use_rviz')
    stm32_port = LaunchConfiguration('stm32_port')
    stm32_baudrate = LaunchConfiguration('stm32_baudrate')
    resolution = LaunchConfiguration('resolution')

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

    # ─── 4. Cartographer 3D 建图节点 ──────────────────────────
    cartographer_config_dir = os.path.join(czybot_slam_dir, 'config')

    cartographer_node = Node(
        package='cartographer_ros',
        executable='cartographer_node',
        name='cartographer_node',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            '-configuration_directory', cartographer_config_dir,
            '-configuration_basename', 'cartographer_3d.lua',
        ],
        remappings=[
            # 3D模式：直接订阅点云
            ('points2', '/livox/lidar'),
            ('imu', '/livox/imu'),
            ('odom', '/odom'),
        ]
    )

    cartographer_delayed = TimerAction(period=6.0, actions=[cartographer_node])

    # ─── 5. 占据栅格地图节点（3D→2D投影） ──────────────────────
    occupancy_grid_node = Node(
        package='cartographer_ros',
        executable='cartographer_occupancy_grid_node',
        name='cartographer_occupancy_grid_node',
        output='screen',
        parameters=[
            {'use_sim_time': use_sim_time},
            {'resolution': resolution},
        ],
        arguments=['-resolution', resolution, '-publish_period_sec', '1.0']
    )

    occupancy_grid_delayed = TimerAction(period=7.0, actions=[occupancy_grid_node])

    # ─── 6. RViz2 可视化 ──────────────────────────────────────
    rviz_config = os.path.join(czybot_slam_dir, 'rviz', 'slam_3d.rviz')

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
        declare_use_imu,
        declare_resolution,

        LogInfo(msg='[czybot_slam] 启动 Cartographer 3D SLAM...'),
        LogInfo(msg='[czybot_slam] 硬件: RDK S100 + Livox Mid-360S + STM32底盘'),
        LogInfo(msg='[czybot_slam] 3D建图完成后执行: ros2 service call /write_state cartographer_ros_msgs/srv/WriteState "{filename: \'my_map.pbstream\'}"'),

        stm32_bridge_node,
        static_tf_base_to_livox,
        rviz_node,
        livox_delayed,
        cartographer_delayed,
        occupancy_grid_delayed,
    ])
