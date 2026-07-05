#!/bin/bash
########################################
# RDK S100 SLAM 依赖安装 & 编译脚本
# 在 RDK S100 设备上执行
# 用法: bash rdk_slam_setup.sh
########################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $1"; }

ROS_DISTRO="${ROS_DISTRO:-humble}"
WS_DIR="${HOME}/rdks100_slam/ros2_ws"

echo ""
echo "========================================"
echo "  RDK S100 SLAM 环境配置脚本"
echo "  ROS2: ${ROS_DISTRO}"
echo "========================================"
echo ""

# ─── Step 1: 检查ROS2环境 ──────────────────────────────────────
log_step "[1/5] 检查 ROS2 ${ROS_DISTRO} 环境..."
if [ ! -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]; then
    log_error "未找到 ROS2 ${ROS_DISTRO}，请先安装 ROS2"
    exit 1
fi
source /opt/ros/${ROS_DISTRO}/setup.bash
log_info "ROS2 ${ROS_DISTRO} 已就绪"

# ─── Step 2: 安装系统依赖 ──────────────────────────────────────
log_step "[2/5] 安装 SLAM 依赖包..."
sudo apt-get update -q

# Cartographer
log_info "安装 cartographer_ros..."
sudo apt-get install -y \
    ros-${ROS_DISTRO}-cartographer \
    ros-${ROS_DISTRO}-cartographer-ros \
    ros-${ROS_DISTRO}-cartographer-ros-msgs

# slam_toolbox
log_info "安装 slam_toolbox..."
sudo apt-get install -y ros-${ROS_DISTRO}-slam-toolbox

# pointcloud_to_laserscan（点云转2D激光）
log_info "安装 pointcloud_to_laserscan..."
sudo apt-get install -y ros-${ROS_DISTRO}-pointcloud-to-laserscan

# 导航地图工具
log_info "安装 nav2_map_server..."
sudo apt-get install -y \
    ros-${ROS_DISTRO}-nav2-map-server \
    ros-${ROS_DISTRO}-nav2-lifecycle-manager

# TF工具
sudo apt-get install -y \
    ros-${ROS_DISTRO}-tf2-ros \
    ros-${ROS_DISTRO}-tf2-tools

# Python串口（STM32通信）
sudo apt-get install -y python3-serial

log_info "所有依赖安装完成"

# ─── Step 3: 编译工作空间 ──────────────────────────────────────
log_step "[3/5] 编译 ROS2 工作空间..."
if [ ! -d "${WS_DIR}" ]; then
    log_error "工作空间不存在: ${WS_DIR}"
    log_error "请先执行 deploy.sh 将代码传输到设备"
    exit 1
fi

cd "${WS_DIR}"

# 清理旧编译缓存（可选）
read -p "是否清理旧编译缓存？(y/N): " clean_choice
clean_choice=${clean_choice:-N}
if [ "$clean_choice" = "y" ] || [ "$clean_choice" = "Y" ]; then
    rm -rf build install log
    log_info "已清理旧编译缓存"
fi

log_info "开始编译（首次约需5~15分钟）..."
colcon build \
    --symlink-install \
    --cmake-args -DCMAKE_BUILD_TYPE=Release \
    --packages-select \
        livox_ros_driver2 \
        czybot_navigation2 \
        czybot_slam

if [ $? -eq 0 ]; then
    log_info "编译成功！"
else
    log_error "编译失败，请检查错误信息"
    exit 1
fi

# ─── Step 4: 配置环境变量 ──────────────────────────────────────
log_step "[4/5] 配置 .bashrc 环境变量..."

SETUP_LINE="source ${WS_DIR}/install/setup.bash"
ALIAS_LINE="alias slam_2d='ros2 launch czybot_slam cartographer_2d_slam.launch.py'"
ALIAS_LINE2="alias slam_3d='ros2 launch czybot_slam cartographer_3d_slam.launch.py'"
ALIAS_LINE3="alias save_map='bash ${HOME}/rdks100_slam/ros2_ws/src/czybot_slam/scripts/save_map.sh'"

if ! grep -q "${SETUP_LINE}" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# RDK S100 SLAM 工作空间" >> ~/.bashrc
    echo "${SETUP_LINE}" >> ~/.bashrc
    echo "${ALIAS_LINE}" >> ~/.bashrc
    echo "${ALIAS_LINE2}" >> ~/.bashrc
    echo "${ALIAS_LINE3}" >> ~/.bashrc
    log_info "已添加环境变量到 .bashrc"
else
    log_info ".bashrc 已包含工作空间配置，跳过"
fi

# ─── Step 5: 配置Livox网络 ────────────────────────────────────
log_step "[5/5] 检查 Livox Mid-360S 网络配置..."
echo ""
log_warn "Livox Mid-360S 需要静态IP配置:"
log_warn "  设备IP: 192.168.1.138"
log_warn "  主机IP: 192.168.1.50 (需设置在连接360S的网口上)"
echo ""
log_warn "配置主机网口命令示例（根据实际网口名替换 eth0）:"
echo "  sudo ip addr add 192.168.1.50/24 dev eth0"
echo "  sudo ip link set eth0 up"
echo ""
log_warn "或通过 nmcli 设置持久化静态IP:"
echo "  sudo nmcli con mod '有线连接 1' ipv4.method manual ipv4.addresses 192.168.1.50/24"
echo "  sudo nmcli con up '有线连接 1'"
echo ""

# 检查是否已有192.168.1.x的网口
if ip addr | grep -q "192.168.1."; then
    log_info "检测到 192.168.1.x 网络配置已存在"
    ip addr | grep "192.168.1."
else
    log_warn "未检测到 192.168.1.x 网络，请手动配置"
fi

# ─── 完成 ──────────────────────────────────────────────────────
echo ""
echo "========================================"
echo -e "${GREEN}  SLAM 环境配置完成！${NC}"
echo "========================================"
echo ""
echo "重新加载环境变量："
echo "  source ~/.bashrc"
echo ""
echo "启动建图（推荐2D模式）："
echo "  slam_2d"
echo "  # 或"
echo "  ros2 launch czybot_slam cartographer_2d_slam.launch.py"
echo ""
echo "保存地图："
echo "  save_map  # 或指定名称: save_map my_room"
echo ""
echo "启动3D建图："
echo "  slam_3d"
echo ""
