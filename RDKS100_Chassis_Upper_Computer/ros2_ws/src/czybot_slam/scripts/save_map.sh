#!/bin/bash
########################################
# SLAM 地图保存脚本
# 用法: bash save_map.sh [地图名称]
# 默认保存到 ~/rdks100_slam/my_map/ 目录
########################################

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 配置
MAP_DIR="${HOME}/rdks100_slam/my_map"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MAP_NAME="${1:-map_${TIMESTAMP}}"

echo ""
echo "========================================"
echo "  SLAM 地图保存工具"
echo "========================================"
echo ""

# 确保目录存在
mkdir -p "${MAP_DIR}"

# 检查 map_saver_cli 是否可用
if ! command -v ros2 &>/dev/null; then
    echo -e "${RED}错误: ros2 命令不可用，请先source ROS2环境${NC}"
    exit 1
fi

echo -e "${YELLOW}[INFO] 保存地图: ${MAP_NAME}${NC}"
echo -e "${YELLOW}[INFO] 保存路径: ${MAP_DIR}/${MAP_NAME}${NC}"
echo ""

# 保存地图（nav2_map_server）
# ⚠️ save_map_timeout 必须是 double 类型，整数会报类型错误（ROS2 Humble）
ros2 run nav2_map_server map_saver_cli \
    -f "${MAP_DIR}/${MAP_NAME}" \
    --ros-args -p save_map_timeout:=10000.0

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ 地图保存成功！${NC}"
    echo -e "${GREEN}  PGM文件: ${MAP_DIR}/${MAP_NAME}.pgm${NC}"
    echo -e "${GREEN}  YAML文件: ${MAP_DIR}/${MAP_NAME}.yaml${NC}"
    echo ""
    
    # 同时保存一份为 my_map（最新地图）
    cp "${MAP_DIR}/${MAP_NAME}.pgm" "${MAP_DIR}/my_map.pgm"
    cp "${MAP_DIR}/${MAP_NAME}.yaml" "${MAP_DIR}/my_map.yaml"
    # 更新yaml中的image字段指向
    sed -i "s|image:.*|image: my_map.pgm|" "${MAP_DIR}/my_map.yaml"
    
    echo -e "${GREEN}✓ 已同步更新 my_map.pgm / my_map.yaml（最新地图副本）${NC}"
    echo ""
    echo "地图文件列表:"
    ls -la "${MAP_DIR}"/*.pgm "${MAP_DIR}"/*.yaml 2>/dev/null
else
    echo -e "${RED}✗ 地图保存失败！${NC}"
    echo -e "${RED}  请检查SLAM是否在运行中，/map话题是否有数据${NC}"
    echo ""
    echo "调试命令:"
    echo "  ros2 topic list | grep map"
    echo "  ros2 topic echo /map --once"
    exit 1
fi

echo ""
echo "========================================"
echo "  提示：后续导航使用地图"
echo "  ros2 launch nav2_bringup bringup_launch.py \\"
echo "    map:=${MAP_DIR}/my_map.yaml"
echo "========================================"
