# =============================================================================
# API 路由：机器人控制
# =============================================================================
# 控制链路（统一安全门面 SafetyGate）：
#   前端 → (HTTP /api/control/velocity 或 WS cmd_vel)
#        → safety_gate.filter()  ← 限速/死区/急停锁
#        → ros2_bridge.publish_cmd_vel() → /cmd_vel
#        → stm32_bridge → STM32（再次限幅 + 超时停车）
#
#   急停：
#   前端 → (HTTP /api/control/stop 或 WS estop)
#        → safety_gate.trigger_estop()  ← 设置锁，期间过滤所有非零速
#        → ros2_bridge.publish_estop() → /cmd_vel_estop（Empty）
#        → stm32_bridge 立即连发零速
#        → 同时 publish_cmd_vel(0,0,0) 兜底
#
# 速度上限与死区集中在 app.core.config，与 STM32 USER/ChassisParams.h 一致：
#   ROBOT_MAX_LINEAR_VEL  = 0.60 m/s
#   ROBOT_MAX_ANGULAR_VEL = 1.20 rad/s
# =============================================================================

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import (
    ROBOT_MAX_LINEAR_VEL, ROBOT_MAX_ANGULAR_VEL,
    ROBOT_DEFAULT_LINEAR_VEL, ROBOT_DEFAULT_ANGULAR_VEL,
    ROBOT_LINEAR_DEADBAND, ROBOT_ANGULAR_DEADBAND,
    ROBOT_ESTOP_LOCK_SECONDS, ROBOT_CMD_WATCHDOG_SECONDS,
)
from app.services.mock_data import mock_generator
from app.services.ros2_bridge import ros2_bridge
from app.services.safety_gate import safety_gate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/control", tags=["control"])

# 当前手动模式速度（仅用于 mock 显示）
_current_vx: float = 0.0
_current_wz: float = 0.0


class VelocityCmd(BaseModel):
    linear_x: float = Field(
        0.0,
        ge=-ROBOT_MAX_LINEAR_VEL,
        le=ROBOT_MAX_LINEAR_VEL,
        description="线速度 m/s",
    )
    linear_y: float = Field(
        0.0,
        ge=-ROBOT_MAX_LINEAR_VEL,
        le=ROBOT_MAX_LINEAR_VEL,
        description="横向速度 m/s（阿克曼底盘忽略）",
    )
    angular_z: float = Field(
        0.0,
        ge=-ROBOT_MAX_ANGULAR_VEL,
        le=ROBOT_MAX_ANGULAR_VEL,
        description="角速度 rad/s",
    )


class ModeCmd(BaseModel):
    mode: str = Field(..., description="运行模式: manual / auto / navigation")


# -----------------------------------------------------------------------------
# 速度控制（HTTP fallback；主通道为 WebSocket）
# -----------------------------------------------------------------------------
@router.post("/velocity", summary="发送速度控制指令（HTTP fallback，主通道为 WebSocket）")
async def set_velocity(cmd: VelocityCmd):
    global _current_vx, _current_wz

    vx, vy, wz, allowed = safety_gate.filter(cmd.linear_x, cmd.linear_y, cmd.angular_z)
    if not allowed:
        # 急停锁中：拒绝转发，但不返回 HTTP 错误，前端仍可继续轮询
        logger.debug("[Control] 急停锁中，丢弃速度请求")
        return {
            "success": False,
            "estop_locked": True,
            "data": {"linear_x": 0.0, "linear_y": 0.0, "angular_z": 0.0},
        }

    _current_vx = vx
    _current_wz = wz

    mock_generator.set_velocity(vx, vy, wz)
    if ros2_bridge.is_enabled:
        ros2_bridge.publish_cmd_vel(vx, vy, wz)

    return {
        "success": True,
        "data": {"linear_x": vx, "linear_y": vy, "angular_z": wz},
    }


# -----------------------------------------------------------------------------
# 急停（HTTP 独立通道）
# -----------------------------------------------------------------------------
@router.post("/stop", summary="急停（HTTP 独立通道，不受 WebSocket 速度指令影响）")
async def emergency_stop():
    """
    急停：
      1. 触发 SafetyGate 急停锁（ROBOT_ESTOP_LOCK_SECONDS 内拒绝任何非零速）
      2. ros2_bridge.publish_estop() → stm32_bridge 立即连发零速并锁定
      3. 同时连发 5 帧 cmd_vel(0,0,0) 兜底
    """
    global _current_vx, _current_wz
    _current_vx = 0.0
    _current_wz = 0.0

    safety_gate.trigger_estop("api:/stop")
    mock_generator.emergency_stop()

    if ros2_bridge.is_enabled:
        loop = asyncio.get_event_loop()

        def _send_stop_frames():
            import time
            try:
                ros2_bridge.publish_estop()
            except Exception as e:
                logger.warning("[Control] publish_estop 失败: %s", e)
            for i in range(5):
                try:
                    ros2_bridge.publish_cmd_vel(0.0, 0.0, 0.0)
                except Exception as e:
                    logger.warning("[Control] 急停发送第 %d 帧失败: %s", i + 1, e)
                time.sleep(0.02)

        await loop.run_in_executor(None, _send_stop_frames)
        logger.info("[Control] 急停：已触发 SafetyGate + 5 帧零速 + estop topic")

    return {"success": True, "message": "急停指令已执行"}


# -----------------------------------------------------------------------------
# 模式
# -----------------------------------------------------------------------------
@router.post("/mode", summary="切换运行模式")
async def set_mode(cmd: ModeCmd):
    allowed = {"manual", "auto", "navigation"}
    if cmd.mode not in allowed:
        raise HTTPException(status_code=400, detail=f"无效模式，允许值: {allowed}")
    return {"success": True, "mode": cmd.mode}


# -----------------------------------------------------------------------------
# 控制参数（前端用于 UI 限制对齐）
# -----------------------------------------------------------------------------
@router.get("/params", summary="获取控制参数")
async def get_control_params():
    return {
        "max_linear_vel": ROBOT_MAX_LINEAR_VEL,
        "max_angular_vel": ROBOT_MAX_ANGULAR_VEL,
        "default_linear_vel": ROBOT_DEFAULT_LINEAR_VEL,
        "default_angular_vel": ROBOT_DEFAULT_ANGULAR_VEL,
        "linear_deadband": ROBOT_LINEAR_DEADBAND,
        "angular_deadband": ROBOT_ANGULAR_DEADBAND,
        "estop_lock_seconds": ROBOT_ESTOP_LOCK_SECONDS,
        "cmd_watchdog_seconds": ROBOT_CMD_WATCHDOG_SECONDS,
    }
