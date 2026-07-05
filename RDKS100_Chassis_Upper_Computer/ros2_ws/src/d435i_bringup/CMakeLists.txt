cmake_minimum_required(VERSION 3.8)
project(d435i_bringup)

find_package(ament_cmake REQUIRED)

# 安装 launch 文件
install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

# 安装 config 文件
install(DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

ament_package()
