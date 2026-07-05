#!/bin/bash
# =============================================================================
# S100 激光雷达 ROS2 工作空间编译脚本
# 用法: bash build_ros2_ws.sh
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS2_WS="${SCRIPT_DIR}/ros2_ws"

echo "========================================"
echo "  RDK S100 雷达 ROS2 工作空间编译"
echo "========================================"
echo ""

# 1. 检查 ROS2 环境
echo -e "${YELLOW}[1/4] 检查 ROS2 环境...${NC}"
if [ -f /opt/ros/humble/setup.bash ]; then
    source /opt/ros/humble/setup.bash
    echo -e "${GREEN}ROS2 Humble 环境已加载${NC}"
else
    echo -e "${RED}错误: 未找到 /opt/ros/humble/setup.bash${NC}"
    echo "请确认 ROS2 Humble 已安装"
    exit 1
fi

# 2. 安装依赖（仅首次需要）
echo ""
echo -e "${YELLOW}[2/4] 检查并安装系统依赖...${NC}"

REQUIRED_PKGS=(
    "python3-serial"
    "ros-humble-tf2-ros"
    "ros-humble-tf2-tools"
)

MISSING_PKGS=()
for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo "需要安装: ${MISSING_PKGS[*]}"
    sudo apt-get update
    sudo apt-get install -y "${MISSING_PKGS[@]}"
else
    echo -e "${GREEN}基础依赖已满足${NC}"
fi

# 3. 编译
echo ""
echo -e "${YELLOW}[3/4] 编译 ROS2 工作空间...${NC}"
cd "${ROS2_WS}"
colcon build --symlink-install

if [ $? -eq 0 ]; then
    echo -e "${GREEN}编译成功！${NC}"
else
    echo -e "${RED}编译失败，请检查错误信息${NC}"
    exit 1
fi

# 4. 添加环境变量到 .bashrc
echo ""
echo -e "${YELLOW}[4/4] 配置环境变量...${NC}"
SOURCE_LINE="source ${ROS2_WS}/install/setup.bash"
if ! grep -qF "${SOURCE_LINE}" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# RDK S100 雷达工作空间" >> ~/.bashrc
    echo "${SOURCE_LINE}" >> ~/.bashrc
    echo -e "${GREEN}已添加到 ~/.bashrc${NC}"
else
    echo -e "${GREEN}~/.bashrc 中已存在，跳过${NC}"
fi

# 加载当前 shell
source "${ROS2_WS}/install/setup.bash"

echo ""
echo "========================================"
echo "  编译完成！"
echo "========================================"
echo ""
echo "测试雷达驱动："
echo "  ros2 launch ldlidar ld14p.launch.py"
echo ""
echo "查看 /scan 数据："
echo "  ros2 topic echo /scan --once"
echo ""
echo "启动 SLAM 建图："
echo "  ros2 launch ldlidar slam_mapping.launch.py"
echo ""
