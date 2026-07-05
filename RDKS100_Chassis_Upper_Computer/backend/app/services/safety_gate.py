# =============================================================================
# 安全门面（SafetyGate）—— 后端统一速度控制入口
# =============================================================================
# 所有发往 STM32（经由 ros2_bridge → /cmd_vel）的速度请求都必须经过本模块。
# 模块内部统一处理：
#   1. 与 STM32 ChassisParams.h 一致的硬限幅 (ROBOT_MAX_LINEAR_VEL / ROBOT_MAX_ANGULAR_VEL)
#   2. 与下位机对齐的死区过滤 (ROBOT_LINEAR_DEADBAND / ROBOT_ANGULAR_DEADBAND)
#   3. 急停锁：触发急停后 ROBOT_ESTOP_LOCK_SECONDS 内禁止发非零速
#   4. Watchdog：后端独立线程，若超过 ROBOT_CMD_WATCHDOG_SECONDS 没有任何
#      手动 cmd_vel/estop 调用，主动给 ros2_bridge 发零速兜底
#
# 这样手动控制（HTTP / WebSocket）和导航相关接口都走同一道安全门，
# 即使前端断开 / 浏览器关闭 / FastAPI 异常，后端也能确保 STM32 收到停车指令。
# =============================================================================

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

from app.core.config import (
    ROBOT_MAX_LINEAR_VEL,
    ROBOT_MAX_ANGULAR_VEL,
    ROBOT_LINEAR_DEADBAND,
    ROBOT_ANGULAR_DEADBAND,
    ROBOT_ESTOP_LOCK_SECONDS,
    ROBOT_CMD_WATCHDOG_SECONDS,
)

logger = logging.getLogger(__name__)


class SafetyGate:
    """统一速度控制门面（线程安全）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._estop_until: float = 0.0
        self._last_cmd_time: float = 0.0
        self._last_vx: float = 0.0
        self._last_wz: float = 0.0

        # watchdog
        self._wd_thread: Optional[threading.Thread] = None
        self._wd_running = False
        self._wd_publisher = None  # 注入：ros2_bridge.publish_cmd_vel

    # ── 初始化 ──────────────────────────────────────────────────────────────
    def bind_publisher(self, publish_cmd_vel):
        """注入底层发布函数；通常是 ros2_bridge.publish_cmd_vel"""
        self._wd_publisher = publish_cmd_vel

    def start_watchdog(self):
        """启动后端 watchdog 线程（仅启动一次）"""
        if self._wd_thread and self._wd_thread.is_alive():
            return
        self._wd_running = True
        self._wd_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="safety_wd"
        )
        self._wd_thread.start()
        logger.info(
            "[Safety] watchdog 已启动，超时=%.2fs，限速=%.2fm/s / %.2frad/s",
            ROBOT_CMD_WATCHDOG_SECONDS,
            ROBOT_MAX_LINEAR_VEL,
            ROBOT_MAX_ANGULAR_VEL,
        )

    def stop_watchdog(self):
        self._wd_running = False
        if self._wd_thread:
            self._wd_thread.join(timeout=1.0)

    # ── 速度入口 ────────────────────────────────────────────────────────────
    def filter(self, vx: float, vy: float, wz: float) -> Tuple[float, float, float, bool]:
        """
        对单次速度请求执行限速 + 死区 + 急停锁过滤。
        返回 (vx, vy, wz, allowed)：
          allowed=False 表示急停锁定中，强制返回 (0, 0, 0)。
        """
        now = time.time()
        with self._lock:
            estop_active = now < self._estop_until

        if estop_active:
            return 0.0, 0.0, 0.0, False

        # 硬限幅
        vx = max(-ROBOT_MAX_LINEAR_VEL, min(ROBOT_MAX_LINEAR_VEL, float(vx)))
        vy = max(-ROBOT_MAX_LINEAR_VEL, min(ROBOT_MAX_LINEAR_VEL, float(vy)))
        wz = max(-ROBOT_MAX_ANGULAR_VEL, min(ROBOT_MAX_ANGULAR_VEL, float(wz)))

        # 死区
        if abs(vx) < ROBOT_LINEAR_DEADBAND:
            vx = 0.0
        if abs(vy) < ROBOT_LINEAR_DEADBAND:
            vy = 0.0
        if abs(wz) < ROBOT_ANGULAR_DEADBAND:
            wz = 0.0

        with self._lock:
            self._last_cmd_time = now
            self._last_vx = vx
            self._last_wz = wz

        return vx, vy, wz, True

    def trigger_estop(self, source: str = "unknown") -> float:
        """
        触发急停，返回急停锁定解除时刻。
        允许多次调用：后调用的会重置锁定窗口。
        """
        until = time.time() + ROBOT_ESTOP_LOCK_SECONDS
        with self._lock:
            self._estop_until = until
            self._last_vx = 0.0
            self._last_wz = 0.0
            self._last_cmd_time = time.time()
        logger.warning("[Safety] 急停触发 source=%s 锁定至 +%.2fs", source,
                       ROBOT_ESTOP_LOCK_SECONDS)
        return until

    def is_estop_active(self) -> bool:
        with self._lock:
            return time.time() < self._estop_until

    # ── Watchdog ───────────────────────────────────────────────────────────
    def _watchdog_loop(self):
        check_interval = max(0.05, ROBOT_CMD_WATCHDOG_SECONDS / 3.0)
        last_wd_stop_ts = 0.0

        while self._wd_running:
            time.sleep(check_interval)

            with self._lock:
                last_t = self._last_cmd_time
                last_vx = self._last_vx
                last_wz = self._last_wz

            if last_t == 0.0:
                continue

            elapsed = time.time() - last_t
            if elapsed <= ROBOT_CMD_WATCHDOG_SECONDS:
                continue

            # 只在最近一次发的不是零、且距离上次 watchdog 停车 > 1s 时再发
            need_stop = (abs(last_vx) > 1e-6 or abs(last_wz) > 1e-6)
            if need_stop and (time.time() - last_wd_stop_ts > 1.0):
                logger.warning(
                    "[Safety][WD] 后端 %.2fs 未收到任何控制指令，自动发零速",
                    elapsed,
                )
                if self._wd_publisher:
                    try:
                        self._wd_publisher(0.0, 0.0, 0.0)
                    except Exception as e:
                        logger.error("[Safety][WD] 发布零速失败: %s", e)
                with self._lock:
                    self._last_vx = 0.0
                    self._last_wz = 0.0
                last_wd_stop_ts = time.time()


# 全局单例
safety_gate = SafetyGate()
