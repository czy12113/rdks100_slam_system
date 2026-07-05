#!/bin/bash
# STM32串口通信诊断脚本
# 在RDK S100上运行:
#   bash diagnose_stm32.sh [/dev/ttyUSB0] [115200]

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  STM32 串口通信诊断工具${NC}"
echo -e "${BLUE}========================================${NC}"

PORT="${1:-${STM32_PORT:-/dev/ttyUSB0}}"
BAUD="${2:-${STM32_BAUDRATE:-115200}}"

echo -e "  目标串口: ${GREEN}${PORT}${NC}"
echo -e "  目标波特率: ${GREEN}${BAUD}${NC}"

# ── 步骤1：检查串口设备 ──────────────────────────────────────────
echo -e "\n${YELLOW}[1/5] 检查串口设备...${NC}"
for dev in /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyACM0; do
    if [ -e "$dev" ]; then
        echo -e "  ${GREEN}✓ $dev 存在${NC}"
        # 显示设备信息
        udevadm info --name=$dev --attribute-walk 2>/dev/null | grep -E "idVendor|idProduct|manufacturer|product" | head -4 | sed 's/^/    /'
    else
        echo -e "  ${RED}✗ $dev 不存在${NC}"
    fi
done

# ── 步骤2：检查串口占用 ──────────────────────────────────────────
echo -e "\n${YELLOW}[2/5] 检查串口占用情况...${NC}"
for dev in /dev/ttyUSB0 /dev/ttyUSB1; do
    if [ -e "$dev" ]; then
        PIDS=$(lsof $dev 2>/dev/null | awk 'NR>1 {print $1, $2}')
        if [ -n "$PIDS" ]; then
            echo -e "  ${YELLOW}⚠ $dev 被占用:${NC}"
            echo "$PIDS" | sed 's/^/    /'
        else
            echo -e "  ${GREEN}✓ $dev 未被占用${NC}"
        fi
    fi
done

# ── 步骤3：发送测试命令并监听响应 ──────────────────────────────────
echo -e "\n${YELLOW}[3/5] 向 ${PORT} 发送速度命令并监听响应...${NC}"
echo -e "  协议格式: AA 55 01 [linear_int16_LE] [angular_int16_LE] 00 [checksum] 0D"
echo -e "  发送: 前进 200mm/s (AA 55 01 C8 00 00 00 00 C9 0D)"

if [ ! -e "$PORT" ]; then
    echo -e "  ${RED}✗ ${PORT} 不存在，跳过${NC}"
else
    # 配置串口
    stty -F "$PORT" "$BAUD" raw -echo cs8 -cstopb -parenb 2>/dev/null

    # 构造帧: AA 55 01 C8 00 00 00 00 C9 0D
    # linear=200(0x00C8 LE), angular=0, reserved=0x00
    # checksum = (0x01 + 0xC8 + 0x00 + 0x00 + 0x00 + 0x00) & 0xFF = 0xC9
    CMD='\xAA\x55\x01\xC8\x00\x00\x00\x00\xC9\x0D'

    echo -e "  正在发送命令..."
    printf "$CMD" > "$PORT"

    echo -e "  等待STM32响应 (2秒)..."
    RESPONSE=$(timeout 2 cat "$PORT" | xxd | head -5)

    if [ -n "$RESPONSE" ]; then
        echo -e "  ${GREEN}✓ 收到STM32响应:${NC}"
        echo "$RESPONSE" | sed 's/^/    /'
    else
        echo -e "  ${RED}✗ 未收到STM32响应${NC}"
        echo -e "  ${YELLOW}  可能原因: STM32未上电/固件未运行/波特率不匹配/接线错误${NC}"
    fi

    # 发送停止命令
    # linear=0, angular=0, checksum=0x01
    STOP='\xAA\x55\x01\x00\x00\x00\x00\x00\x01\x0D'
    for _ in $(seq 1 15); do
        printf "$STOP" > "$PORT"
        sleep 0.02
    done
    echo -e "  已发送 15 帧停止命令"
fi

# ── 步骤4：监听STM32主动发送的数据 ──────────────────────────────────
echo -e "\n${YELLOW}[4/5] 监听 ${PORT} 主动发送的数据 (3秒)...${NC}"
echo -e "  期望格式: BB 66 01 [pos_x 4B] [pos_y 4B] [yaw 2B] [vx 2B] [vth 2B] [reserved 2B] [checksum] 0D"

if [ -e "$PORT" ]; then
    stty -F "$PORT" "$BAUD" raw -echo 2>/dev/null
    DATA=$(timeout 3 cat "$PORT" | xxd | head -10)
    if [ -n "$DATA" ]; then
        echo -e "  ${GREEN}✓ 收到数据:${NC}"
        echo "$DATA" | sed 's/^/    /'
    else
        echo -e "  ${RED}✗ 3秒内未收到任何数据${NC}"
        echo -e "  ${YELLOW}  STM32可能未上电或未发送里程计数据${NC}"
    fi
fi

# ── 步骤5：检查ROS节点和话题 ──────────────────────────────────────
echo -e "\n${YELLOW}[5/5] 检查ROS2状态...${NC}"

# 检查ROS2环境
if ! command -v ros2 &>/dev/null; then
    echo -e "  ${RED}✗ ros2命令不可用，请先 source /opt/ros/humble/setup.bash${NC}"
else
    # 检查节点
    NODES=$(ros2 node list 2>/dev/null)
    if echo "$NODES" | grep -q "stm32_bridge"; then
        echo -e "  ${GREEN}✓ /stm32_bridge 节点运行中${NC}"
    else
        echo -e "  ${RED}✗ /stm32_bridge 节点未运行${NC}"
    fi
    if echo "$NODES" | grep -q "tjc_hmi_bridge"; then
        echo -e "  ${GREEN}✓ /tjc_hmi_bridge 节点运行中（串口屏，可选）${NC}"
    else
        echo -e "  ${YELLOW}- /tjc_hmi_bridge 未运行（串口屏链路，可忽略）${NC}"
    fi

    # 检查/cmd_vel订阅者
    CMD_VEL_INFO=$(ros2 topic info /cmd_vel 2>/dev/null)
    if [ -n "$CMD_VEL_INFO" ]; then
        SUB_COUNT=$(echo "$CMD_VEL_INFO" | grep "Subscription count" | awk '{print $3}')
        echo -e "  ${GREEN}✓ /cmd_vel 话题存在，订阅者数量: $SUB_COUNT${NC}"
    else
        echo -e "  ${RED}✗ /cmd_vel 话题不存在${NC}"
    fi

    if echo "$NODES" | grep -q "stm32_bridge"; then
        echo -e "  ${BLUE}stm32_bridge 参数:${NC}"
        ros2 param get /stm32_bridge port 2>/dev/null | sed 's/^/    /' || true
        ros2 param get /stm32_bridge baudrate 2>/dev/null | sed 's/^/    /' || true
    fi
fi

echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}  诊断完成${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}下一步排查建议:${NC}"
echo "  1. 如果步骤3/4无响应 → STM32串口通信有问题，检查端口、波特率、固件协议"
echo "  2. 如果步骤3/4有响应 → STM32正常，问题在ROS节点"
echo "  3. 如果串口被占用 → 先停止占用进程再测试"
echo "  4. 可尝试: bash diagnose_stm32.sh /dev/ttyUSB0 9600 或 /dev/ttyUSB1 115200"
