#!/usr/bin/env python3
"""
真实小车 Nav2 导航启动文件（Livox Mid-360S 版本）
================================================
硬件：RDK S100 + Livox Mid-360S + STM32 阿克曼底盘
依赖：先用 `czybot_slam` 跑 `cartographer_2d_slam.launch.py` 建好地图并保存成
      ~/rdks100_slam/my_map/my_map.yaml（默认）。

本 launch 启动顺序与 SLAM 严格对齐，只是把 Cartographer 换成了 Nav2 + AMCL：

    stm32_bridge（publish_tf=True 发 odom→base_link）
      └── static_transform_publisher (base_link → livox_frame)
            └── livox_ros_driver2                (5s 后)
                  └── pointcloud_to_laserscan    (7s 后, /scan)
                        └── scan_dedup           (7.5s 后, /scan_dedup)
                              └── scan_filter    (8s 后, /scan_filtered)
                                    └── nav2_bringup (9s 后, 含 map_server + amcl
                                                      + planner + controller …)
                                          └── rviz2  (12s 后)

说明：
  * Nav2 与 SLAM 的 odom→base_link 一律由 stm32_bridge 提供，AMCL 负责
    map→odom。这一点和 SLAM 模式（Cartographer 自己掌管 SLAM TF）正好相反，
    所以 publish_tf 在两边互斥。
  * 默认地图路径与 czybot_slam/scripts/save_map.sh 的输出一致：
        ~/rdks100_slam/my_map/my_map.yaml
    如果地图在别处，启动时 `map:=/path/to/your.yaml` 覆盖即可。

常用启动命令：
  ros2 launch czybot_navigation2 livox_navigation.launch.py
  ros2 launch czybot_navigation2 livox_navigation.launch.py \
      map:=/home/kkk/rdks100_slam/my_map/my_map.yaml use_rviz:=false

调参建议：
  * 第一次开机若车不在地图原点，请用 RViz 的 “2D Pose Estimate” 重新定位，
    或者通过 `initial_pose_x/y/yaw` 参数在 launch 时给出初值。
  * 若需要禁用 collision_monitor（仅纯算法验证），把 nav2 的 lifecycle
    list 中的 collision_monitor 去掉即可。

────────────────────────────────────────────────────────────────────────
现场故障排查（参考 运动控制导航问题修改建议.md）：

  Step 0. 确认运行的是源码最新包（重要！install/share 经常残留旧 yaml）
      cd ~/rdks100_slam/ros2_ws
      colcon build --packages-select czybot_navigation2 czybot_slam --symlink-install
      source install/setup.bash
      ros2 pkg prefix czybot_navigation2   # prefix 必须是当前工作区 install

  Step 1. /cmd_vel 单发布单订阅检查
      ros2 topic info /cmd_vel -v
      ros2 node info /stm32_bridge
      期望：/cmd_vel 至少有 /stm32_bridge 一个订阅者；
            发布者只有 controller_server（或 collision_monitor，二者择一）。

  Step 2. 绕开 Nav2 验证底盘
      ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
          "{linear: {x: 0.25}, angular: {z: 0.0}}"
      同时另开终端：
      ros2 topic echo /stm32_bridge/tx_cmd      # 看 bridge 实际写入的 mm/s
      ros2 topic echo /odom                     # 看 STM32 回报的速度
      ros2 run tf2_ros tf2_echo odom base_link  # 看 TF 是否前进

      判定：
        - /stm32_bridge/tx_cmd 没值或全 0     → bridge 入口被死区/急停/超时清零，
                                                看 stm32_bridge 1Hz [OBS] 日志定位
        - tx_cmd 非零 / odom 不变             → 串口/STM32/电机/编码器问题
        - odom 变 / TF 不变                   → bridge 的 publish_tf 链路问题
        - 都变但 Nav2 仍报 progress failed    → AMCL/costmap/progress checker 问题

  Step 3. 最小链路（仅 controller_server → /cmd_vel → stm32_bridge）
      当前 nav2_params.yaml 已经把 collision_monitor.cmd_vel_out_topic 改成
      /cmd_vel_collision_monitor（实质禁用），velocity_smoother 也旁路。
      因此 /cmd_vel 只有 controller_server 一个发布者，stm32_bridge 一个订阅者，
      满足建议文档 Section 5 的"最小验证链"。底盘验证通过后再恢复全链路。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
from nav2_common.launch import RewrittenYaml


def generate_launch_description():
    czybot_slam_dir = get_package_share_directory('czybot_slam')
    czybot_nav_dir = get_package_share_directory('czybot_navigation2')
    livox_driver_dir = get_package_share_directory('livox_ros_driver2')
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')

    # ──────────────────────────────────────────────────────────────────
    # Launch 参数
    # ──────────────────────────────────────────────────────────────────
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('use_rviz')
    map_yaml = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')
    autostart = LaunchConfiguration('autostart')
    use_composition = LaunchConfiguration('use_composition')
    use_respawn = LaunchConfiguration('use_respawn')

    stm32_port = LaunchConfiguration('stm32_port')
    stm32_baudrate = LaunchConfiguration('stm32_baudrate')

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

    default_map = os.path.join(
        os.path.expanduser('~'), 'rdks100_slam', 'my_map', 'my_map.yaml'
    )
    default_params = os.path.join(czybot_nav_dir, 'config', 'nav2_params.yaml')
    default_rviz = os.path.join(czybot_nav_dir, 'config', 'nav2_view.rviz')

    declared_arguments = [
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use simulation clock',
        ),
        DeclareLaunchArgument(
            'use_rviz',
            # ★ RK S100 板载跑 RViz 会和 Livox/Nav2 抢内存，引发 SIGSEGV 段错误。
            #   默认关闭板载 RViz，需要可视化请在远程机器（PC/笔记本）开 RViz：
            #     export ROS_DOMAIN_ID=<同板子>
            #     rviz2 -d <czybot_navigation2/config/nav2_view.rviz>
            #   或者临时启用：ros2 launch ... use_rviz:=true
            default_value='false',
            description='Start RViz2 (RK 板算力紧张，默认关闭，建议远程开)',
        ),
        DeclareLaunchArgument(
            'map',
            default_value=default_map,
            description='Full path to map yaml file (output of save_map.sh)',
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Nav2 parameter file',
        ),
        DeclareLaunchArgument(
            'autostart',
            default_value='true',
            description='Automatically activate Nav2 lifecycle nodes',
        ),
        # Humble 的 component_container_isolated 在加载 global_costmap 时偶发
        # "Node already added to an executor"，关掉 composition 用独立进程更稳。
        DeclareLaunchArgument(
            'use_composition',
            default_value='False',
            description='Run Nav2 in single composable container',
        ),
        DeclareLaunchArgument(
            'use_respawn',
            default_value='False',
            description='Respawn Nav2 nodes if they crash',
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
        # ── v5：抑制冲过 + 终点摆动的关键参数 ──────────────────────────
        # min_motion_linear：bridge 把 0 < |v| < 此值 的命令抬升到此值，
        # 用来开过电机静摩擦。值过大 → MPPI 减速段失效（冲过目标）。
        # 演进：v3=0.18（车不动→冲过）→ v4=0.10（仍有过冲）→ v5=0.08
        # v5 配合 MPPI vx_max=0.15 → 调速带宽 [0.08, 0.15]，
        # 减速可分辨率 ≈ 0.07 m/s，足够 MPPI 在终点平滑减速到 0。
        # 调试建议：
        #   - 实测 0.08 m/s 电机能稳定起步 → 保持 0.08
        #   - 0.08 命令电机原地不动 → 升到 0.10，但 nav2_params.yaml 里
        #     的 vx_max 也要同步升到 0.18，保证带宽 ≥ 0.08 m/s
        DeclareLaunchArgument(
            'stm32_min_motion_linear',
            default_value='0.08',
            description='Bridge 启动门槛 (m/s)，v5 配合 vx_max=0.15 使用',
        ),
        DeclareLaunchArgument(
            'stm32_linear_deadzone',
            default_value='0.005',
            description='线速度死区 (m/s)，低于此值视为 0',
        ),
        # v11.0：angular_deadzone 默认 0.010 → 0.002
        # 解决"只直走、不拐小角度"中 ROS 侧第一道死区把 MPPI 微转向
        # 命令清零的问题（1° 修正只需 ω≈0.017 rad/s，落在 0.010 死区内）。
        # STM32 端 ANGULAR_DEADBAND=0.03 是第二道死区，需在 Keil 同步降到
        # 0.005 才能彻底解锁。详见 运动控制导航问题修改建议.md v11.0 节。
        DeclareLaunchArgument(
            'stm32_angular_deadzone',
            default_value='0.002',
            description='角速度死区 (rad/s)，v11.0 起降到 0.002 以解锁小角度修正',
        ),
        # 与 SLAM launch 完全相同的雷达外参与滤波链参数，便于复用调参成果
        DeclareLaunchArgument('lidar_x', default_value='0.0'),
        DeclareLaunchArgument('lidar_y', default_value='0.0'),
        # ★ v6.3 修正：Livox Mid-360S 离地实测 0.25 m（之前 0.15 m 是过时值）
        #   注意：这是 base_link → livox_frame 的静态 TF Z 偏移。
        #   base_link 默认在车轮接地面（z=0），雷达水平扫描层因此落在地图 z=0.25。
        #   修正后 RViz 中雷达可视化位置与车体实际安装位置一致；
        #   对 2D 导航的避障决策无功能性影响（投影到 z=0 后的 LaserScan 不变）。
        #   如车架结构变动导致雷达高度变化，请通过命令行参数 lidar_z:=<新值> 覆盖。
        DeclareLaunchArgument('lidar_z', default_value='0.25'),
        DeclareLaunchArgument('lidar_qx', default_value='0.0'),
        DeclareLaunchArgument('lidar_qy', default_value='0.0'),
        DeclareLaunchArgument('lidar_qz', default_value='0.0'),
        DeclareLaunchArgument('lidar_qw', default_value='1.0'),
        DeclareLaunchArgument('scan_min_height', default_value='0.15'),
        DeclareLaunchArgument('scan_max_height', default_value='0.90'),
        # ★ RK S100 减负：angle_increment 从 0.25°(0.00436)→1.5°(0.02618)，
        #   scan 数组从 1440 → 240 点，下游 costmap/AMCL/MPPI 处理量直接降 6 倍。
        #   1.5° 分辨率对 0.35 m/s 室内导航完全足够（@5m 距离对应 13cm 横向分辨）。
        DeclareLaunchArgument('scan_angle_increment', default_value='0.02617994'),
        # ★ 雷达远端杂点是局部 costmap 误检主因，限到 8m 即可
        DeclareLaunchArgument('scan_range_max', default_value='8.0'),
        DeclareLaunchArgument('scan_dedup_min_interval_ms', default_value='80.0'),
        DeclareLaunchArgument('rewrite_scan_stamps', default_value='true'),
        DeclareLaunchArgument('scan_filter_range_max', default_value='8.0'),
        DeclareLaunchArgument('scan_filter_neighbor_radius', default_value='2'),
        DeclareLaunchArgument('scan_filter_min_neighbors', default_value='1'),
        DeclareLaunchArgument('scan_filter_max_neighbor_delta', default_value='0.45'),
        DeclareLaunchArgument('scan_filter_temporal_min_hits', default_value='2'),
        DeclareLaunchArgument('scan_filter_temporal_delta', default_value='0.50'),
    ]

    # ──────────────────────────────────────────────────────────────────
    # 1. STM32 桥接：负责 odom→base_link TF + /odom + 接收 /cmd_vel
    # ──────────────────────────────────────────────────────────────────
    stm32_min_motion_linear = LaunchConfiguration('stm32_min_motion_linear')
    stm32_linear_deadzone = LaunchConfiguration('stm32_linear_deadzone')
    stm32_angular_deadzone = LaunchConfiguration('stm32_angular_deadzone')

    stm32_bridge_node = Node(
        package='czybot_navigation2',
        executable='stm32_bridge',
        name='stm32_bridge',
        output='screen',
        # ★ v6.2 回退：stm32_bridge 直接订阅 /cmd_vel
        # ────────────────────────────────────────────────────────
        # v6 曾尝试 remap 到 /cmd_vel_safe 想把 collision_monitor 串入
        # 控制链。但 nav2_bringup 的默认 lifecycle 列表里并不包含
        # collision_monitor（它是独立的 nav2_collision_monitor 包，
        # 需要单独 launch 并由 lifecycle_manager 接管才会激活）。
        # 这导致 /cmd_vel_safe 没有任何发布者，stm32_bridge 永远收不到
        # 速度命令，小车不动。
        # v6.2 回退到最小可动链路：
        #   controller_server → /cmd_vel → stm32_bridge → STM32
        # MPPI 自身的避障由 CostCritic（cost_weight=18.0 + critical_cost=220
        # + inflation_radius=0.40）保证。
        # 如未来要真正启用 collision_monitor 物理避障兜底，需要：
        #   1. 在 launch 里单独 Node(package='nav2_collision_monitor',...)
        #   2. 把 collision_monitor 加进 lifecycle_manager_navigation 的
        #      node_names 列表里激活
        #   3. 然后再恢复这里的 remap=('cmd_vel','cmd_vel_safe')
        parameters=[{
            'port': stm32_port,
            'baudrate': ParameterValue(stm32_baudrate, value_type=int),
            # 导航模式必须打开 TF：AMCL 提供 map→odom，STM32 提供 odom→base_link
            'publish_tf': True,
            # ★ v6.9 强制开环 odom（修复 AMCL "图标钉死 + 激光跟车飘"）
            # ────────────────────────────────────────────────────────
            # 现场实测 STM32 端 #define ODOMETRY_READ_ENCODER = 0 时，
            # 固件仍在以 10Hz 发上行 odom 帧，但帧里 pos_x/pos_y/yaw 字段
            # 恒为 0（因为没编码器读数）。
            #
            # 默认 odom_source='auto' 的逻辑是：STM32 还在按时上行就让位、
            # 让 _parse_odom_data 接管发布。结果：
            #   - /odom 一直发零位姿
            #   - odom→base_link TF 锁死在 (0,0,0)
            #   - AMCL 触发更新需要 odom 位姿增量 → 永远不更新
            #   - map→odom TF 锁死在初始 2D Pose Estimate 值
            #   - 现象：RViz 车图标钉死、激光点云随车物理运动飘
            #
            # 改 'open_loop' 后，bridge 无视 STM32 的零位姿帧，
            # 用最近一次写入串口的 last_tx_v / last_tx_w 做差分积分，
            # 20Hz 发出连续可用的 /odom + TF，AMCL 才能持续更新。
            #
            # ※ v7.0 闭环 odom 方案现场验证失败 (小车速度仍被锁死), 已回滚.
            #   保留 'open_loop' 是当前稳定方案. 后续若再启动闭环, 需要先
            #   把 I2C 改成分段状态机 (方案 B), 才能彻底消除编码器读对
            #   控制帧的阻塞.
            'odom_source': 'open_loop',
            # ★ v4 抑制超调：让 bridge 启动门槛与 MPPI 减速带宽匹配
            # 见上方 DeclareLaunchArgument 注释。运行时可覆盖：
            #   ros2 launch ... stm32_min_motion_linear:=0.08
            'min_motion_linear': ParameterValue(
                stm32_min_motion_linear, value_type=float
            ),
            'linear_deadzone': ParameterValue(
                stm32_linear_deadzone, value_type=float
            ),
            'angular_deadzone': ParameterValue(
                stm32_angular_deadzone, value_type=float
            ),
        }],
    )

    # ──────────────────────────────────────────────────────────────────
    # 2. 雷达静态外参 + Livox 驱动 + 点云转激光 + 去重 + 滤波
    #    这 5 个节点与 czybot_slam 的 SLAM launch 完全等价，仅顺序与延迟。
    # ──────────────────────────────────────────────────────────────────
    static_tf_base_to_livox = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_base_to_livox',
        arguments=[
            lidar_x, lidar_y, lidar_z,
            lidar_qx, lidar_qy, lidar_qz, lidar_qw,
            'base_link', 'livox_frame',
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
        # ★ Livox 驱动偶发 SIGSEGV（exit code -11），开启 respawn 自动拉起，
        #   避免一旦驱动崩溃导致整套 Nav2 失效。respawn_delay 给 2s 防止
        #   持续 crash loop 抢占 CPU。
        respawn=True,
        respawn_delay=2.0,
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

    # ──────────────────────────────────────────────────────────────────
    # 3. Nav2 全家桶（map_server + amcl + planner + controller + smoother
    #    + behavior + bt_navigator + waypoint_follower + velocity_smoother
    #    + collision_monitor + lifecycle_manager）
    # ──────────────────────────────────────────────────────────────────
    # 阿克曼专用 BT XML 的绝对路径（位于 install/share 下，编译后存在）
    bt_xml_nav_to_pose = os.path.join(
        czybot_nav_dir, 'behavior_trees', 'navigate_to_pose_ackermann.xml'
    )
    bt_xml_nav_through_poses = os.path.join(
        czybot_nav_dir, 'behavior_trees', 'navigate_through_poses_ackermann.xml'
    )

    # nav2 的 bt_navigator 在 yaml 里写 launch substitution 不会被展开，
    # 这里通过 RewrittenYaml 在 launch 时把绝对路径注入到参数文件副本里。
    configured_params = RewrittenYaml(
        source_file=params_file,
        root_key='',
        param_rewrites={
            'default_nav_to_pose_bt_xml': bt_xml_nav_to_pose,
            'default_nav_through_poses_bt_xml': bt_xml_nav_through_poses,
        },
        convert_types=True,
    )

    # ──────────────────────────────────────────────────────────────────
    # ★ v6 控制链路（关键修复"撞向障碍物"问题）：
    #   controller_server   → /cmd_vel
    #     collision_monitor → /cmd_vel_safe
    #       stm32_bridge    → STM32 (订 /cmd_vel_safe，通过上方 remap)
    #
    # collision_monitor 在 nav2_params.yaml 中配置：
    #   cmd_vel_in_topic:  cmd_vel
    #   cmd_vel_out_topic: cmd_vel_safe
    # 它根据 /scan_filtered 检测前方 1.5s 内可能碰撞的距离，
    # 把通过的线速度按比例缩放到 0，作为 MPPI 之外的物理避障兜底。
    #
    # 这种方案的好处：不需要修改 nav2_bringup 的内部封装，
    # 只通过 stm32_bridge 的 remap 把 collision_monitor 串入链路。
    # ──────────────────────────────────────────────────────────────────
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

    # ──────────────────────────────────────────────────────────────────
    # 4. RViz（可选）
    # ──────────────────────────────────────────────────────────────────
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
        LogInfo(msg='[czybot_navigation2] Livox + Nav2 starting.'),
        LogInfo(msg='[czybot_navigation2] STM32 publishes odom->base_link, '
                     'AMCL publishes map->odom.'),
        LogInfo(msg='[czybot_navigation2] RViz disabled by default on RK S100 '
                     '(use use_rviz:=true 或远程机器打开).'),
        stm32_bridge_node,
        static_tf_base_to_livox,
        # ★ 延长各阶段启动间隔，让上一节点的 TF/topic 完全稳定后再起下一个，
        # 修复 "Lookup would require extrapolation into the past" —— 该错误
        # 的根因是 Nav2 启动时 odom→base_link TF 还没填满 buffer。
        TimerAction(period=3.0, actions=[livox_driver_node]),
        TimerAction(period=6.0, actions=[pointcloud_to_laserscan_node]),
        TimerAction(period=6.5, actions=[scan_dedup_node]),
        TimerAction(period=7.0, actions=[scan_filter_node]),
        # 等 stm32_bridge 持续发 odom→base_link 至少 5s，且 /scan_filtered
        # 稳定输出后再启 Nav2，否则全局 costmap 一上来就报 TF 外推错误
        TimerAction(period=12.0, actions=[nav2_bringup]),
        TimerAction(period=18.0, actions=[rviz_node]),
    ])
