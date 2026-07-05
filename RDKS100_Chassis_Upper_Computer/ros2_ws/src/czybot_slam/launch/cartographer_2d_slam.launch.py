#!/usr/bin/env python3

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    czybot_slam_dir = get_package_share_directory('czybot_slam')
    livox_driver_dir = get_package_share_directory('livox_ros_driver2')

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('use_rviz')
    stm32_port = LaunchConfiguration('stm32_port')
    stm32_baudrate = LaunchConfiguration('stm32_baudrate')
    resolution = LaunchConfiguration('resolution')
    publish_period_sec = LaunchConfiguration('publish_period_sec')

    lidar_x = LaunchConfiguration('lidar_x')
    lidar_y = LaunchConfiguration('lidar_y')
    lidar_z = LaunchConfiguration('lidar_z')
    lidar_qx = LaunchConfiguration('lidar_qx')
    lidar_qy = LaunchConfiguration('lidar_qy')
    lidar_qz = LaunchConfiguration('lidar_qz')
    lidar_qw = LaunchConfiguration('lidar_qw')

    scan_min_height = LaunchConfiguration('scan_min_height')
    scan_max_height = LaunchConfiguration('scan_max_height')
    scan_angle_increment = LaunchConfiguration('scan_angle_increment')
    scan_range_max = LaunchConfiguration('scan_range_max')
    scan_dedup_min_interval_ms = LaunchConfiguration('scan_dedup_min_interval_ms')
    rewrite_scan_stamps = LaunchConfiguration('rewrite_scan_stamps')
    scan_filter_range_max = LaunchConfiguration('scan_filter_range_max')
    scan_filter_neighbor_radius = LaunchConfiguration('scan_filter_neighbor_radius')
    scan_filter_min_neighbors = LaunchConfiguration('scan_filter_min_neighbors')
    scan_filter_max_neighbor_delta = LaunchConfiguration(
        'scan_filter_max_neighbor_delta'
    )
    scan_filter_temporal_min_hits = LaunchConfiguration(
        'scan_filter_temporal_min_hits'
    )
    scan_filter_temporal_delta = LaunchConfiguration('scan_filter_temporal_delta')

    declared_arguments = [
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use simulation clock',
        ),
        DeclareLaunchArgument(
            'use_rviz',
            default_value='true',
            description='Start RViz2',
        ),
        DeclareLaunchArgument(
            'stm32_port',
            default_value='/dev/ttyUSB0',
            description='STM32 serial port',
        ),
        DeclareLaunchArgument(
            'stm32_baudrate',
            default_value='115200',
            description='STM32 serial baudrate',
        ),
        DeclareLaunchArgument(
            'resolution',
            default_value='0.05',
            description='Occupancy grid resolution in meters',
        ),
        DeclareLaunchArgument(
            'publish_period_sec',
            default_value='1.0',
            description='Occupancy grid publish period',
        ),
        DeclareLaunchArgument(
            'lidar_x',
            default_value='0.0',
            description='Livox x offset from base_link in meters',
        ),
        DeclareLaunchArgument(
            'lidar_y',
            default_value='0.0',
            description='Livox y offset from base_link in meters',
        ),
        DeclareLaunchArgument(
            'lidar_z',
            default_value='0.15',
            description='Livox z offset from base_link in meters',
        ),
        DeclareLaunchArgument(
            'lidar_qx',
            default_value='0.0',
            description='Livox static TF quaternion x',
        ),
        DeclareLaunchArgument(
            'lidar_qy',
            default_value='0.0',
            description='Livox static TF quaternion y',
        ),
        DeclareLaunchArgument(
            'lidar_qz',
            default_value='0.0',
            description='Livox static TF quaternion z',
        ),
        DeclareLaunchArgument(
            'lidar_qw',
            default_value='1.0',
            description='Livox static TF quaternion w',
        ),
        DeclareLaunchArgument(
            'scan_min_height',
            default_value='0.15',
            description='Minimum point height used for LaserScan projection (base_link frame)',
        ),
        DeclareLaunchArgument(
            'scan_max_height',
            default_value='0.90',
            description='Maximum point height used for LaserScan projection (base_link frame)',
        ),
        DeclareLaunchArgument(
            'scan_angle_increment',
            default_value='0.00436332',
            description='Projected LaserScan angle increment in radians',
        ),
        DeclareLaunchArgument(
            'scan_range_max',
            default_value='12.0',
            description='Maximum range used by projected LaserScan',
        ),
        DeclareLaunchArgument(
            'scan_dedup_min_interval_ms',
            default_value='80.0',
            description='Minimum /scan_dedup output interval in milliseconds',
        ),
        DeclareLaunchArgument(
            'rewrite_scan_stamps',
            default_value='true',
            description='Allow scan_dedup to rewrite non-monotonic timestamps',
        ),
        DeclareLaunchArgument(
            'scan_filter_range_max',
            default_value='12.0',
            description='Maximum range kept by scan_filter',
        ),
        DeclareLaunchArgument(
            'scan_filter_neighbor_radius',
            default_value='2',
            description='Neighbor radius used by scan_filter',
        ),
        DeclareLaunchArgument(
            'scan_filter_min_neighbors',
            default_value='1',
            description='Minimum close neighbors required by scan_filter',
        ),
        DeclareLaunchArgument(
            'scan_filter_max_neighbor_delta',
            default_value='0.45',
            description='Maximum range delta for scan_filter neighbor support',
        ),
        DeclareLaunchArgument(
            'scan_filter_temporal_min_hits',
            default_value='2',
            description='Consecutive similar hits required for sparse beams',
        ),
        DeclareLaunchArgument(
            'scan_filter_temporal_delta',
            default_value='0.50',
            description='Maximum temporal range delta for sparse beams',
        ),
    ]

    stm32_bridge_node = Node(
        package='czybot_navigation2',
        executable='stm32_bridge',
        name='stm32_bridge',
        output='screen',
        parameters=[{
            'port': stm32_port,
            'baudrate': stm32_baudrate,
            'publish_tf': False,
        }],
    )

    static_tf_base_to_livox = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_base_to_livox',
        arguments=[
            lidar_x, lidar_y, lidar_z,
            lidar_qx, lidar_qy, lidar_qz, lidar_qw,
            'base_link',
            'livox_frame',
        ],
        output='screen',
    )

    livox_config_path = os.path.join(
        livox_driver_dir, 'config', 'MID360s_config.json'
    )
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
        }],
    )

    pointcloud_to_laserscan_node = Node(
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='pointcloud_to_laserscan',
        output='screen',
        parameters=[
            os.path.join(czybot_slam_dir, 'config', 'pointcloud_to_laserscan.yaml'),
            {
                'use_sim_time': use_sim_time,
                'min_height': ParameterValue(scan_min_height, value_type=float),
                'max_height': ParameterValue(scan_max_height, value_type=float),
                'angle_increment': ParameterValue(
                    scan_angle_increment, value_type=float
                ),
                'range_max': ParameterValue(scan_range_max, value_type=float),
            },
        ],
        remappings=[
            ('cloud_in', '/livox/lidar'),
            ('scan', '/scan'),
        ],
    )

    scan_dedup_node = Node(
        package='czybot_slam',
        executable='scan_dedup.py',
        name='scan_dedup',
        output='screen',
        parameters=[{
            'min_interval_ms': ParameterValue(
                scan_dedup_min_interval_ms, value_type=float
            ),
            'rewrite_stamps': ParameterValue(rewrite_scan_stamps, value_type=bool),
        }],
    )

    scan_filter_node = Node(
        package='czybot_slam',
        executable='scan_filter.py',
        name='scan_filter',
        output='screen',
        parameters=[{
            'input_topic': '/scan_dedup',
            'output_topic': '/scan_filtered',
            'range_min': 0.20,
            'range_max': ParameterValue(scan_filter_range_max, value_type=float),
            'neighbor_radius': ParameterValue(
                scan_filter_neighbor_radius, value_type=int
            ),
            'min_neighbors': ParameterValue(
                scan_filter_min_neighbors, value_type=int
            ),
            'max_neighbor_delta': ParameterValue(
                scan_filter_max_neighbor_delta, value_type=float
            ),
            'temporal_min_hits': ParameterValue(
                scan_filter_temporal_min_hits, value_type=int
            ),
            'temporal_delta': ParameterValue(
                scan_filter_temporal_delta, value_type=float
            ),
            'use_inf': True,
        }],
    )

    cartographer_config_dir = os.path.join(czybot_slam_dir, 'config')
    cartographer_node = Node(
        package='cartographer_ros',
        executable='cartographer_node',
        name='cartographer_node',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            '-configuration_directory', cartographer_config_dir,
            '-configuration_basename', 'cartographer_2d.lua',
        ],
        remappings=[
            ('scan', '/scan_filtered'),
            ('odom', '/odom'),
        ],
    )

    occupancy_grid_node = Node(
        package='cartographer_ros',
        executable='cartographer_occupancy_grid_node',
        name='cartographer_occupancy_grid_node',
        output='screen',
        parameters=[
            {'use_sim_time': use_sim_time},
            {'resolution': resolution},
        ],
        arguments=[
            '-resolution', resolution,
            '-publish_period_sec', publish_period_sec,
        ],
    )

    rviz_config = os.path.join(czybot_slam_dir, 'rviz', 'slam_2d.rviz')
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': use_sim_time}],
        condition=IfCondition(use_rviz),
    )

    return LaunchDescription([
        *declared_arguments,
        LogInfo(msg='[czybot_slam] Starting Cartographer 2D SLAM.'),
        LogInfo(
            msg='[czybot_slam] STM32 TF disabled; Cartographer owns SLAM TF.'
        ),
        LogInfo(
            msg='[czybot_slam] Projecting Livox cloud in base_link and filtering scan outliers.'
        ),
        stm32_bridge_node,
        static_tf_base_to_livox,
        TimerAction(period=3.0, actions=[livox_driver_node]),
        TimerAction(period=5.0, actions=[pointcloud_to_laserscan_node]),
        TimerAction(period=5.5, actions=[scan_dedup_node]),
        TimerAction(period=6.0, actions=[scan_filter_node]),
        TimerAction(period=7.0, actions=[cartographer_node]),
        TimerAction(period=8.0, actions=[occupancy_grid_node]),
        TimerAction(period=9.0, actions=[rviz_node]),
    ])
