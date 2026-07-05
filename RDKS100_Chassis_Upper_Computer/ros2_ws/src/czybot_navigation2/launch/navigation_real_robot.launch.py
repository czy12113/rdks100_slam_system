#!/usr/bin/env python3
"""
真实小车导航启动文件
硬件配置：RDK S100 + Livox Mid-360S激光雷达 + STM32底盘
功能：启动雷达驱动、STM32通信、Nav2导航栈
前提：需要先用slam_real_robot.launch.py建好地图
使用方法：ros2 launch czybot_navigation2 navigation_real_robot.launch.py map:=/path/to/your/map.yaml
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.conditions import IfCondition
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    # 参数声明
    use_sim_time = LaunchConfiguration('use_sim_time')
    map_yaml_file = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')
    lidar_port = LaunchConfiguration('lidar_port')
    stm32_port = LaunchConfiguration('stm32_port')
    stm32_baudrate = LaunchConfiguration('stm32_baudrate')
    use_rviz = LaunchConfiguration('use_rviz')
    
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation time'
    )
    
    declare_map_yaml = DeclareLaunchArgument(
        'map',
        default_value=PathJoinSubstitution([
            FindPackageShare('czybot_navigation2'),
            'maps',
            'room.yaml'
        ]),
        description='Full path to map yaml file'
    )
    
    declare_params_file = DeclareLaunchArgument(
        'params_file',
        default_value=PathJoinSubstitution([
            FindPackageShare('czybot_navigation2'),
            'config',
            'nav2_params.yaml'
        ]),
        description='Full path to the ROS2 parameters file for Nav2'
    )
    
    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Launch RViz2 (set to false if not needed)'
    )
    
    declare_stm32_baudrate = DeclareLaunchArgument(
        'stm32_baudrate',
        default_value='115200',
        description='STM32 serial baudrate (9600 or 115200)'
    )
    
    declare_lidar_port = DeclareLaunchArgument(
        'lidar_port',
        default_value='/dev/ttyCH343USB0',
        description='LD14P laser serial port'
    )
    
    declare_stm32_port = DeclareLaunchArgument(
        'stm32_port',
        default_value='/dev/ttyUSB0',
        description='STM32 serial port'
    )
    
    # 1. STM32串口通信桥接节点（先启动，确保TF就绪）
    stm32_bridge_node = Node(
        package='czybot_navigation2',
        executable='stm32_bridge',
        name='stm32_bridge',
        output='screen',
        parameters=[{
            'port': stm32_port,
            'baudrate': ParameterValue(stm32_baudrate, value_type=int),
            'publish_tf': True,  # 使用真实里程计发布TF
        }]
    )
    
    # 2. LD14P 雷达驱动（使用ldlidar官方launch，包含雷达节点和静态TF）
    ldlidar_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ldlidar'),
                'launch',
                'ld14p.launch.py'
            ])
        ]),
        launch_arguments={
            'port_name': lidar_port,
        }.items()
    )
    
    # 延迟启动激光雷达，确保STM32的TF已经发布
    ld14p_delayed = TimerAction(
        period=5.0,
        actions=[ldlidar_launch]
    )
    
    # 3. Nav2 导航栈
    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('nav2_bringup'),
                'launch',
                'bringup_launch.py'
            ])
        ]),
        launch_arguments={
            'map': map_yaml_file,
            'use_sim_time': use_sim_time,
            'params_file': params_file,
            'autostart': 'true',
        }.items()
    )
    
    # 延迟启动Nav2，确保传感器和TF都就绪
    nav2_delayed = TimerAction(
        period=8.0,  # 等待雷达和TF完全就绪
        actions=[nav2_launch]
    )
    
    # 4. RViz2 可视化（可选）
    rviz_config = PathJoinSubstitution([
        FindPackageShare('nav2_bringup'),
        'rviz',
        'nav2_default_view.rviz'
    ])
    
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen',
        condition=IfCondition(use_rviz)
    )
    
    return LaunchDescription([
        declare_use_sim_time,
        declare_map_yaml,
        declare_params_file,
        declare_use_rviz,
        declare_lidar_port,
        declare_stm32_port,
        declare_stm32_baudrate,
        stm32_bridge_node,
        ld14p_delayed,
        nav2_delayed,
        rviz_node,
    ])
