-- Cartographer 手持雷达专用配置
-- 完全基于激光扫描匹配，不依赖里程计、IMU或机器人
-- 适用于LD14P手持建图

include "map_builder.lua"
include "trajectory_builder.lua"

options = {
  map_builder = MAP_BUILDER,
  trajectory_builder = TRAJECTORY_BUILDER,
  map_frame = "map",
  tracking_frame = "base_link",
  published_frame = "base_link",  -- 直接发布base_link
  odom_frame = "odom",
  provide_odom_frame = true,  -- Cartographer自己提供odom->base_link
  publish_frame_projected_to_2d = false,
  use_pose_extrapolator = true,
  use_odometry = false,  -- 关键！不使用外部里程计
  use_nav_sat = false,
  use_landmarks = false,
  num_laser_scans = 1,
  num_multi_echo_laser_scans = 0,
  num_subdivisions_per_laser_scan = 1,
  num_point_clouds = 0,
  lookup_transform_timeout_sec = 0.5,
  submap_publish_period_sec = 0.3,
  pose_publish_period_sec = 5e-3,  -- 200Hz发布位姿
  trajectory_publish_period_sec = 30e-3,
  rangefinder_sampling_ratio = 1.0,  -- 处理所有scan数据
  odometry_sampling_ratio = 1.0,
  fixed_frame_pose_sampling_ratio = 1.0,
  imu_sampling_ratio = 1.0,
  landmarks_sampling_ratio = 1.0,
}

-- 使用2D SLAM
MAP_BUILDER.use_trajectory_builder_2d = true

-- 2D轨迹构建器配置
TRAJECTORY_BUILDER_2D.use_imu_data = false  -- 不使用IMU

-- LD14P雷达参数
TRAJECTORY_BUILDER_2D.min_range = 0.1
TRAJECTORY_BUILDER_2D.max_range = 12.0
TRAJECTORY_BUILDER_2D.missing_data_ray_length = 5.0

-- 关键！启用在线扫描匹配（手持建图必须）
TRAJECTORY_BUILDER_2D.use_online_correlative_scan_matching = true

-- 实时扫描匹配器 - 增大搜索窗口以应对手持移动
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.linear_search_window = 0.3  -- 30cm搜索窗口
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.angular_search_window = math.rad(45.)  -- 45度搜索
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.translation_delta_cost_weight = 10.
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.rotation_delta_cost_weight = 1e-1

-- Ceres扫描匹配器 - 精细匹配
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.occupied_space_weight = 10.  -- 增加占用空间权重
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 20.  -- 增加平移权重
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.rotation_weight = 40.  -- 增加旋转权重
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.use_nonmonotonic_steps = false
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.max_num_iterations = 30  -- 增加迭代次数
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.num_threads = 1

-- 运动滤波器 - 极低阈值，对微小移动敏感
TRAJECTORY_BUILDER_2D.motion_filter.max_time_seconds = 0.1  -- 100ms
TRAJECTORY_BUILDER_2D.motion_filter.max_distance_meters = 0.01  -- 1cm就处理！
TRAJECTORY_BUILDER_2D.motion_filter.max_angle_radians = math.rad(1.)  -- 1度就处理！

-- 子图配置
TRAJECTORY_BUILDER_2D.submaps.num_range_data = 60  -- 减少每个子图的扫描数，更频繁创建子图
TRAJECTORY_BUILDER_2D.submaps.grid_options_2d.grid_type = "PROBABILITY_GRID"
TRAJECTORY_BUILDER_2D.submaps.grid_options_2d.resolution = 0.05  -- 5cm分辨率

-- 范围数据插入器
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.insert_free_space = true
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.hit_probability = 0.55
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.miss_probability = 0.49

-- 位姿图优化 - 更频繁的优化
POSE_GRAPH.optimize_every_n_nodes = 60  -- 每60个节点优化一次
POSE_GRAPH.constraint_builder.min_score = 0.50  -- 降低约束分数阈值
POSE_GRAPH.constraint_builder.global_localization_min_score = 0.55

-- 优化问题权重
POSE_GRAPH.optimization_problem.huber_scale = 1e1
POSE_GRAPH.optimization_problem.acceleration_weight = 1e3
POSE_GRAPH.optimization_problem.rotation_weight = 3e5

-- 约束构建器 - 增大搜索范围
POSE_GRAPH.constraint_builder.max_constraint_distance = 20.  -- 20米约束距离
POSE_GRAPH.constraint_builder.sampling_ratio = 0.5  -- 增加采样率

-- 快速相关扫描匹配器
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher.linear_search_window = 10.  -- 10米搜索窗口
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher.angular_search_window = math.rad(45.)  -- 45度
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher.branch_and_bound_depth = 7

-- Ceres扫描匹配器（用于回环检测）
POSE_GRAPH.constraint_builder.ceres_scan_matcher.occupied_space_weight = 20.
POSE_GRAPH.constraint_builder.ceres_scan_matcher.translation_weight = 10.
POSE_GRAPH.constraint_builder.ceres_scan_matcher.rotation_weight = 1.
POSE_GRAPH.constraint_builder.ceres_scan_matcher.ceres_solver_options.use_nonmonotonic_steps = true
POSE_GRAPH.constraint_builder.ceres_scan_matcher.ceres_solver_options.max_num_iterations = 10
POSE_GRAPH.constraint_builder.ceres_scan_matcher.ceres_solver_options.num_threads = 1

return options
