cmake_minimum_required(VERSION 3.8)
project(czybot_slam)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

# 安装配置文件、launch文件、rviz配置、脚本
install(DIRECTORY
  config
  launch
  rviz
  scripts
  DESTINATION share/${PROJECT_NAME}
  USE_SOURCE_PERMISSIONS
)

# 安装地图保存脚本为可执行
install(PROGRAMS scripts/save_map.sh DESTINATION lib/${PROJECT_NAME} RENAME save_map)

# 安装 Python 可执行脚本
install(PROGRAMS
  scripts/scan_dedup.py
  scripts/scan_filter.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
