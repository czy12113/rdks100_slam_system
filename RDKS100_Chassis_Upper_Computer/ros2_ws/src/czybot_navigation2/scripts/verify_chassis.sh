#!/usr/bin/env bash
# =============================================================================
# verify_chassis.sh —— 底盘 / cmd_vel / odom / TF 现场分层验证脚本
# -----------------------------------------------------------------------------
# 配套文档：
#   src/czybot_navigation2/运动控制导航问题修改建议.md
#
# 用法（按顺序逐 step 执行，每步看完输出再 Ctrl-C 进下一步）：
#   ./verify_chassis.sh pkg          # Step 0：确认实际加载的是当前工作区
#   ./verify_chassis.sh topo         # Step 1：/cmd_vel 单发布单订阅检查
#   ./verify_chassis.sh tx           # Step 2-a：观察 bridge 实际写串口的整数速度
#   ./verify_chassis.sh obs          # Step 2-b：跟随 stm32_bridge 1Hz 观测日志
#   ./verify_chassis.sh odom         # Step 2-c：底盘上行的 /odom
#   ./verify_chassis.sh tf           # Step 2-d：odom→base_link TF
#   ./verify_chassis.sh drive [v]    # Step 3：手动以 v m/s 发 /cmd_vel（默认 0.25）
#   ./verify_chassis.sh stop         # 给 /cmd_vel_estop 发空消息急停
#   ./verify_chassis.sh all          # 顺序执行 pkg + topo（只读检查）
#
# 期望与故障判定（与建议文档 Section 5 对齐）：
#   /cmd_vel 非零、/odom 不变           → 底盘执行链路问题（串口/STM32/电机）
#   /cmd_vel 为零或断续                 → Nav2 控制链或 collision_monitor 问题
#   /odom 变但 TF 不变                  → stm32_bridge TF 发布问题
#   /odom 与 TF 都变但 Nav2 progress 失败 → AMCL/map/local costmap 或 progress checker
# =============================================================================
set -u

PKG="czybot_navigation2"
TOPIC_CMD="/cmd_vel"
TOPIC_TX="/stm32_bridge/tx_cmd"
TOPIC_ODOM="/odom"
TOPIC_ESTOP="/cmd_vel_estop"
NODE_BRIDGE="/stm32_bridge"

cmd="${1:-help}"

case "$cmd" in
  pkg)
    echo "── Step 0：实际加载的包前缀（应该指向当前工作区 install） ──"
    ros2 pkg prefix "$PKG" || true
    ros2 pkg prefix czybot_slam || true
    echo
    echo "── 期望前缀：~/rdks100_slam/ros2_ws/install/${PKG}"
    echo "  若不是请重新构建并 source：colcon build --symlink-install && source install/setup.bash"
    ;;

  topo)
    echo "── Step 1：${TOPIC_CMD} 拓扑（发布者/订阅者必须各自唯一）──"
    ros2 topic info "$TOPIC_CMD" -v
    echo
    echo "── ${NODE_BRIDGE} 节点信息 ──"
    ros2 node info "$NODE_BRIDGE" || true
    ;;

  tx)
    echo "── Step 2-a：${TOPIC_TX}（bridge 实际写串口的 mm/s 与 mrad/s）──"
    echo "Ctrl-C 退出。"
    ros2 topic echo "$TOPIC_TX"
    ;;

  obs)
    echo "── Step 2-b：跟踪 stm32_bridge 1Hz [OBS] 日志 ──"
    echo "Ctrl-C 退出。"
    # rqt 不一定有，直接 ros2 node 日志通过 topic /rosout 过滤
    ros2 topic echo /rosout --field msg | grep --line-buffered '\[OBS\]'
    ;;

  odom)
    echo "── Step 2-c：${TOPIC_ODOM}.twist.twist（看车体速度反馈）──"
    echo "Ctrl-C 退出。"
    ros2 topic echo "$TOPIC_ODOM" --field twist.twist
    ;;

  tf)
    echo "── Step 2-d：odom → base_link TF ──"
    echo "Ctrl-C 退出。"
    ros2 run tf2_ros tf2_echo odom base_link
    ;;

  drive)
    v="${2:-0.25}"
    echo "── Step 3：以 ${v} m/s 直行手动发 ${TOPIC_CMD} ──"
    echo "Ctrl-C 退出后请立刻执行 ./verify_chassis.sh stop 关停。"
    ros2 topic pub -r 10 "$TOPIC_CMD" geometry_msgs/msg/Twist \
      "{linear: {x: ${v}, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
    ;;

  stop)
    echo "── 急停：向 ${TOPIC_ESTOP} 发空消息 ──"
    ros2 topic pub --once "$TOPIC_ESTOP" std_msgs/msg/Empty "{}"
    echo "（可选）补一次零速 cmd_vel："
    ros2 topic pub --once "$TOPIC_CMD" geometry_msgs/msg/Twist \
      "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
    ;;

  all)
    "$0" pkg
    echo
    "$0" topo
    ;;

  help|*)
    sed -n '1,30p' "$0"
    ;;
esac
