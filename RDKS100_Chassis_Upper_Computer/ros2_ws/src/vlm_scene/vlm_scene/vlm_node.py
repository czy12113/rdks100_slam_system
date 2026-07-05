#!/usr/bin/env python3
"""
vlm_node.py — VLM 场景理解 ROS2 节点
====================================

订阅：
  /camera/camera/color/image_raw           sensor_msgs/Image   原始 RGB 关键帧
  /detection/results                       std_msgs/String     YOLO/DOSOD 检测 JSON

发布：
  /vlm/scene_description                   std_msgs/String     场景描述 JSON
  /vlm/status                              std_msgs/String     节点状态 JSON（启动 / provider / 错误）

ROS2 Service（可选，用于前端手动触发）：
  /vlm/ask                                 std_srvs/Trigger    立刻基于最新一帧做一次推理

整体管线：
  detection_results ──┐
                       ├─ KeyframeSelector.decide() ─ True ─→ provider.describe() ─→ publish
  rgb_image    ──cache┘

设计要点（与项目其它节点一致）：
  - 订阅使用 BEST_EFFORT + depth=1，旧帧 DDS 自动丢；
  - 推理在独立线程内做，避免阻塞 spin；
  - VLM 调用串行 + 节流，永远不会同时发起两个请求。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import queue
import re
import threading
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rcl_interfaces.msg import SetParametersResult
from sensor_msgs.msg import Image
from std_msgs.msg import String
try:
    from std_srvs.srv import Trigger
    _HAS_TRIGGER = True
except Exception:
    _HAS_TRIGGER = False

from .providers import create_provider, list_providers, VLMRequest
from .providers.base import Detection
from .utils import KeyframeSelector, ros_image_to_bgr, downsample_keep_aspect


# ─────────────────────────────────────────────────────────────────────────────
# 火警二次确认默认 Prompt
# 让 VLM 严格输出 JSON，便于后端 / 前端结构化消费
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_FIRE_PROMPT = (
    "你正在协助一台移动机器人做火灾安全监测。\n"
    "一阶检测器（YOLOv5）刚刚在画面里报告了疑似 fire 或 smoke，"
    "但它的误报率较高，常见误报有：橙红色衣物 / 灯光 / 夕阳 / 水蒸气 / 雾 / 电焊 / 屏幕反光等。\n\n"
    "请仔细观察图像，判断**画面里是否真的存在明火或浓烟**，"
    "并以严格 JSON 输出（不要加任何额外文字，不要 markdown 代码块）：\n"
    "{\n"
    '  "level":          "none" | "low" | "high",\n'
    '  "fire_detected":  true | false,\n'
    '  "smoke_detected": true | false,\n'
    '  "confidence":     0~1 之间的小数,\n'
    '  "reason":         "中文一句话，说明判定依据（看到了什么 / 排除了哪些误报）",\n'
    '  "recommendation": "中文一句话，对人员的建议（撤离 / 检查 / 无需处理）"\n'
    "}\n\n"
    "判断标准：\n"
    "  level=high：能明确看到明火（火焰）或大量浓烟，需要立即处理\n"
    "  level=low：有可疑亮光 / 雾气，但难以确定，建议人工核查\n"
    "  level=none：明显是误报（例如灯具 / 衣物 / 反光）\n"
)
# 火警 system_prompt：短小精悍，让 VLM 进入"安全判断"模式
FIRE_SYSTEM_PROMPT = "你是一台具备视觉理解能力的安全监测助手，专注于判定火灾隐患。"


class VLMSceneNode(Node):

    def __init__(self):
        super().__init__("vlm_scene_node")

        # ------------------------------------------------------------------
        # ROS 参数（全部带默认值，可由 config / launch / CLI 覆盖）
        # ------------------------------------------------------------------
        # provider 选择 + 模型名
        self.declare_parameter("provider", "qwen_vl")
        self.declare_parameter("model", "")
        # 订阅 topic
        self.declare_parameter("sub_topic_rgb",       "/camera/camera/color/image_raw")
        self.declare_parameter("sub_topic_detection", "/detection/results")
        # 发布 topic
        self.declare_parameter("pub_topic_description", "/vlm/scene_description")
        self.declare_parameter("pub_topic_status",      "/vlm/status")
        # 节流 / 触发
        self.declare_parameter("cooldown_sec",          3.0)
        self.declare_parameter("heartbeat_sec",        20.0)
        self.declare_parameter("distance_threshold_m",  0.5)
        self.declare_parameter("near_distance_m",       1.0)
        # 输入预处理
        self.declare_parameter("max_image_side",       768)
        self.declare_parameter("min_detections",         1)  # 0 表示无检测也调用 VLM
        self.declare_parameter("max_detections",        10)
        # Prompt
        self.declare_parameter("system_prompt",        "")
        # 网络
        self.declare_parameter("timeout_sec",          20.0)

        # ── 本地轻量化 VLM（internvl_local provider）参数 ────────────────────
        # 这几个参数由 vlm.launch.py 透传，或直接在 vlm_params.yaml 里覆盖。
        # 未声明会导致 launch 传入时抛 ParameterNotDeclaredException，因此这里
        # 全部预先声明；具体读取由 providers/internvl_local.py 通过 env 完成，
        # 节点这一层只负责把 launch 参数写回同名 env（下方 provider 实例化前）。
        self.declare_parameter("local_model_path",     "")
        self.declare_parameter("local_model_type",     "auto")
        self.declare_parameter("local_device",         "auto")
        self.declare_parameter("local_dtype",          "float16")
        self.declare_parameter("local_max_new_tokens", 128)
        self.declare_parameter("local_max_image_side", 448)
        self.declare_parameter("local_stop_distance_m",    0.8)
        self.declare_parameter("local_reroute_distance_m", 2.5)

        # /vlm/ask service 由后端 backend 通过 SetParameters 写入本参数触发定制 prompt。
        # 必须先声明才能被外部 set_parameters 写入。
        self.declare_parameter("next_user_prompt",     "")

        # ── 火警二次确认 ────────────────────────────────────────────────────
        # 订阅 fire_smoke_node 发的 /fire_smoke/prealert
        self.declare_parameter("sub_topic_fire_prealert", "/fire_smoke/prealert")
        # 火警 VLM 推理结果发布到这个 topic（结构化 JSON，前端弹窗用）
        self.declare_parameter("pub_topic_fire_alert",    "/alert/fire")
        # 启用火警二次确认（false 时收到 prealert 也不会调 VLM）
        self.declare_parameter("fire_alert_enabled",      True)
        # 火警 prompt（留空则用 DEFAULT_FIRE_PROMPT）
        self.declare_parameter("fire_alert_prompt",       "")
        # 火警冷却：触发一次告警后 X 秒内忽略新的 prealert，避免刷屏 / 省 token
        self.declare_parameter("fire_alert_cooldown_sec", 15.0)
        # 收到 prealert 后，是否绕过普通触发器节流强制立即推理
        self.declare_parameter("fire_alert_force",        True)
        # 火警告警附带的画面是否 base64 嵌入 /alert/fire 的 JSON 中
        # （前端无需再拉一次图，但消息体会变大约 50KB；后端 WS 也得放行）
        self.declare_parameter("fire_alert_include_image", True)

        self.provider_name      = self.get_parameter("provider").value
        self.model_name         = self.get_parameter("model").value
        self._sub_rgb_topic     = self.get_parameter("sub_topic_rgb").value
        self._sub_det_topic     = self.get_parameter("sub_topic_detection").value
        self._pub_desc_topic    = self.get_parameter("pub_topic_description").value
        self._pub_status_topic  = self.get_parameter("pub_topic_status").value
        self._cooldown          = float(self.get_parameter("cooldown_sec").value)
        self._heartbeat         = float(self.get_parameter("heartbeat_sec").value)
        self._dist_th           = float(self.get_parameter("distance_threshold_m").value)
        self._near_th           = float(self.get_parameter("near_distance_m").value)
        self._max_side          = int(self.get_parameter("max_image_side").value)
        self._min_dets          = int(self.get_parameter("min_detections").value)
        self._max_dets          = int(self.get_parameter("max_detections").value)
        self._system_prompt     = self.get_parameter("system_prompt").value or None
        self._timeout           = float(self.get_parameter("timeout_sec").value)

        # 火警相关
        self._sub_fire_topic    = self.get_parameter("sub_topic_fire_prealert").value
        self._pub_fire_topic    = self.get_parameter("pub_topic_fire_alert").value
        self._fire_enabled      = bool(self.get_parameter("fire_alert_enabled").value)
        self._fire_prompt       = (self.get_parameter("fire_alert_prompt").value
                                    or DEFAULT_FIRE_PROMPT)
        self._fire_cooldown     = float(self.get_parameter("fire_alert_cooldown_sec").value)
        self._fire_force        = bool(self.get_parameter("fire_alert_force").value)
        self._fire_with_image   = bool(self.get_parameter("fire_alert_include_image").value)

        # ------------------------------------------------------------------
        # 把 launch 传进来的 local_* 参数写回环境变量，供 internvl_local provider 读取
        # （provider 自身也支持从 env 读取，这里做二次兜底，让 launch 优先级最高）
        # ------------------------------------------------------------------
        _lp = self.get_parameter("local_model_path").value or ""
        if _lp:
            os.environ["VLM_LOCAL_MODEL_PATH"] = _lp
            # 兼容旧变量名
            os.environ.setdefault("VLM_INTERNVL_MODEL_PATH", _lp)
        _lt = self.get_parameter("local_model_type").value or "auto"
        os.environ["VLM_LOCAL_MODEL_TYPE"] = _lt
        _ldev = self.get_parameter("local_device").value or "auto"
        os.environ["VLM_LOCAL_DEVICE"] = _ldev
        _ldt = self.get_parameter("local_dtype").value or "float16"
        os.environ["VLM_LOCAL_DTYPE"] = _ldt
        try:
            _lmnt = int(self.get_parameter("local_max_new_tokens").value)
            os.environ["VLM_LOCAL_MAX_NEW_TOKENS"] = str(_lmnt)
        except Exception:
            pass

        # 本地 VLM 场景描述节流距离（rule-based fallback / provider 读取）
        try:
            os.environ["VLM_LOCAL_STOP_DISTANCE_M"] = str(
                float(self.get_parameter("local_stop_distance_m").value)
            )
            os.environ["VLM_LOCAL_REROUTE_DISTANCE_M"] = str(
                float(self.get_parameter("local_reroute_distance_m").value)
            )
            os.environ["VLM_LOCAL_MAX_IMAGE_SIDE"] = str(
                int(self.get_parameter("local_max_image_side").value)
            )
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 实例化 Provider
        # ------------------------------------------------------------------
        # provider 实例锁：保护 __init__ / 参数变更回调 / 推理线程之间的 self._provider 切换
        self._provider_lock = threading.Lock()
        provider_kwargs = dict(
            model=self.model_name or None,
            timeout=self._timeout,
            max_image_side=self._max_side,
        )
        self._provider = create_provider(self.provider_name, **provider_kwargs)
        self._provider_ready = self._provider.healthcheck()
        self.get_logger().info(
            f"[VLM] provider={self._provider.name} model={self._provider.model} "
            f"ready={self._provider_ready}（可用: {list_providers()}）"
        )

        # ------------------------------------------------------------------
        # 触发器
        # ------------------------------------------------------------------
        self._selector = KeyframeSelector(
            cooldown_sec=self._cooldown,
            heartbeat_sec=self._heartbeat,
            distance_threshold_m=self._dist_th,
            near_distance_m=self._near_th,
        )

        # ------------------------------------------------------------------
        # 双缓冲：最新 RGB 帧 + 最新检测；推理线程消费
        # ------------------------------------------------------------------
        self._lock = threading.Lock()
        self._latest_bgr: Optional[np.ndarray] = None
        self._latest_bgr_ts: float = 0.0
        self._latest_dets: List[Detection] = []
        self._latest_det_ts: float = 0.0
        self._latest_frame_id: int = 0

        # 强制触发标志（service 调用时置位，附带用户自定义 prompt）
        self._force_lock = threading.Lock()
        self._force_pending: Optional[str] = None  # None = 不强制；str = 用户 prompt

        # ── 火警二次确认状态 ────────────────────────────────────────────────
        # _fire_pending: 收到 /fire_smoke/prealert 时记录 payload；推理线程消费后置 None
        # _last_fire_alert_ts: 上一次成功发出 /alert/fire 的时刻（冷却用）
        self._fire_lock = threading.Lock()
        self._fire_pending: Optional[dict] = None
        self._last_fire_alert_ts: float = 0.0

        # ------------------------------------------------------------------
        # ROS 通信
        # ------------------------------------------------------------------
        qos_sensor = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )
        qos_reliable = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST, depth=10,
        )

        self.create_subscription(Image,  self._sub_rgb_topic,
                                 self._cb_rgb, qos_sensor)
        self.create_subscription(String, self._sub_det_topic,
                                 self._cb_det, qos_reliable)

        self._pub_desc   = self.create_publisher(String, self._pub_desc_topic, 10)
        self._pub_status = self.create_publisher(String, self._pub_status_topic, 10)

        # 火警告警 publisher 永远创建（即便 fire_alert_enabled=False，外部订阅也不会 404）
        self._pub_fire   = self.create_publisher(String, self._pub_fire_topic, 10)
        if self._fire_enabled:
            self.create_subscription(String, self._sub_fire_topic,
                                     self._cb_fire_prealert, qos_reliable)
            self.get_logger().info(
                f"[FIRE] 二次确认已启用 sub={self._sub_fire_topic} "
                f"pub={self._pub_fire_topic} cooldown={self._fire_cooldown:.1f}s "
                f"with_image={self._fire_with_image}"
            )
        else:
            self.get_logger().info("[FIRE] 二次确认已禁用（fire_alert_enabled=False）")

        # 可选 Service：std_srvs/Trigger（无入参，调用后触发一次推理）
        if _HAS_TRIGGER:
            self.create_service(Trigger, "/vlm/ask", self._srv_ask)
            self.get_logger().info("[VLM] /vlm/ask service 已就绪")

        # ------------------------------------------------------------------
        # 推理线程
        # ------------------------------------------------------------------
        self._stop_evt = threading.Event()
        self._thread = threading.Thread(
            target=self._infer_loop, daemon=True, name="vlm_infer",
        )
        self._thread.start()

        # 启动状态广播
        self._publish_status({
            "type": "startup",
            "provider": self._provider.name,
            "model": self._provider.model,
            "ready": self._provider_ready,
            "providers_available": list_providers(),
            "sub": {"rgb": self._sub_rgb_topic, "detection": self._sub_det_topic},
            "pub": {"description": self._pub_desc_topic, "status": self._pub_status_topic},
        })

        # ------------------------------------------------------------------
        # 参数变更回调：让 `ros2 param set /vlm_scene_node provider xxx` 能真正生效
        # ------------------------------------------------------------------
        # 说明：ROS 2 的 param set 只会更新参数值本身，不会重跑 __init__。
        # demo_offline.sh / demo_recover.sh 是通过 `ros2 param set` 切 provider 的，
        # 如果这里不注册回调，节点会一直用启动时创建的那个 provider 实例（比如 qwen_vl），
        # 断网时就永远走云端并报 [Errno 101] Network is unreachable。
        self.add_on_set_parameters_callback(self._on_params_changed)

    # ----------------------------------------------------------------------
    # 参数变更回调
    # ----------------------------------------------------------------------
    def _on_params_changed(self, params) -> SetParametersResult:
        """接收 provider / model 等运行时参数变更，动态重建 self._provider。"""
        # 只关注 provider / model 两个参数；其它参数放行（返回 successful=True 即可）
        new_provider = None
        new_model = None
        for p in params:
            if p.name == "provider":
                try:
                    v = str(p.value or "").strip()
                except Exception:
                    v = ""
                if v:
                    new_provider = v
            elif p.name == "model":
                try:
                    new_model = str(p.value or "")
                except Exception:
                    new_model = ""

        if new_provider is None and new_model is None:
            return SetParametersResult(successful=True)

        target_provider = new_provider or self.provider_name
        target_model = new_model if new_model is not None else self.model_name

        # 与当前完全一致就不重建，避免 healthcheck 抖动
        cur_name = ""
        cur_model = ""
        try:
            cur_name = self._provider.name
            cur_model = self._provider.model or ""
        except Exception:
            pass
        if target_provider == cur_name and (target_model or "") == (cur_model or ""):
            self.get_logger().info(
                f"[VLM] 参数无变化 provider={target_provider} model={target_model or '-'}，跳过重建"
            )
            return SetParametersResult(successful=True)

        self.get_logger().warn(
            f"[VLM] 参数变更 provider: {cur_name} → {target_provider}，"
            f"model: {cur_model or '-'} → {target_model or '-'}，正在重建 provider..."
        )

        try:
            new_kwargs = dict(
                model=target_model or None,
                timeout=self._timeout,
                max_image_side=self._max_side,
            )
            new_inst = create_provider(target_provider, **new_kwargs)
            new_ready = False
            try:
                new_ready = bool(new_inst.healthcheck())
            except Exception as e:
                self.get_logger().warn(f"[VLM] 新 provider healthcheck 失败: {e}")

            # 切实例（拿锁，避免和 _tick_once / _run_fire_alert 竞争）
            old = None
            with self._provider_lock:
                old = self._provider
                self._provider = new_inst
                self._provider_ready = new_ready
                self.provider_name = target_provider
                self.model_name = target_model

            # 优雅关闭旧实例（不在锁内做，避免占锁太久）
            if old is not None and old is not new_inst:
                try:
                    old.close()
                except Exception:
                    pass

            self.get_logger().info(
                f"[VLM] provider 已切换 → name={new_inst.name} model={new_inst.model} "
                f"ready={new_ready}"
            )
            # 广播新的 /vlm/status，前端徽章会立刻更新
            self._publish_status({
                "type": "provider_switched",
                "provider": new_inst.name,
                "model": new_inst.model,
                "ready": new_ready,
                "providers_available": list_providers(),
            })
            return SetParametersResult(successful=True)

        except Exception as e:
            self.get_logger().error(f"[VLM] 参数变更处理失败: {e}")
            # 返回 successful=False 会让 param set 报错，方便脚本感知
            return SetParametersResult(
                successful=False,
                reason=f"rebuild provider failed: {e}",
            )

    # ----------------------------------------------------------------------
    # 订阅回调（在 ROS spin 线程中执行，必须很快返回）
    # ----------------------------------------------------------------------
    def _cb_rgb(self, msg: Image):
        bgr = ros_image_to_bgr(msg)
        if bgr is None:
            return
        ts = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        with self._lock:
            self._latest_bgr = bgr
            self._latest_bgr_ts = ts

    def _cb_det(self, msg: String):
        try:
            data = json.loads(msg.data)
        except Exception as e:
            self.get_logger().warn(f"[VLM] 解析 detection_results 失败: {e}")
            return
        dets = self._parse_detections(data)
        with self._lock:
            self._latest_dets = dets
            self._latest_det_ts = float(data.get("timestamp", 0.0) or 0.0)
            self._latest_frame_id = int(data.get("frame_id", 0) or 0)

    @staticmethod
    def _parse_detections(payload: dict) -> List[Detection]:
        out: List[Detection] = []
        for d in payload.get("detections", []) or []:
            bbox = d.get("bbox") or {}
            try:
                out.append(Detection(
                    class_id=int(d.get("class_id", -1)),
                    class_name=str(d.get("class_name", "unknown")),
                    confidence=float(d.get("confidence", 0.0)),
                    x1=float(bbox.get("x1", 0.0)),
                    y1=float(bbox.get("y1", 0.0)),
                    x2=float(bbox.get("x2", 0.0)),
                    y2=float(bbox.get("y2", 0.0)),
                    distance_m=float(d.get("distance_m", 0.0) or 0.0),
                ))
            except (TypeError, ValueError):
                continue
        # 高置信度优先
        out.sort(key=lambda x: x.confidence, reverse=True)
        return out

    # ----------------------------------------------------------------------
    # 推理主循环
    # ----------------------------------------------------------------------
    def _infer_loop(self):
        while not self._stop_evt.is_set() and rclpy.ok():
            try:
                self._tick_once()
            except Exception as e:
                self.get_logger().error(f"[VLM] 推理循环异常: {e}")
            # 50ms 节流 + 触发器内部 cooldown 双保险
            self._stop_evt.wait(0.05)

    def _tick_once(self):
        # 1. 取出最新一帧 + 检测
        with self._lock:
            bgr = self._latest_bgr.copy() if self._latest_bgr is not None else None
            dets = list(self._latest_dets)
            frame_id = self._latest_frame_id
            ts = self._latest_bgr_ts
        if bgr is None:
            return  # 还没收到图

        # 1.5 火警二次确认优先级最高：若有 prealert，先走火警链路并立即返回
        fire_payload = self._consume_fire_pending()
        if fire_payload is not None:
            self._run_fire_alert(bgr, fire_payload, frame_id, ts)
            return  # 一次 tick 只发一次推理

        # 2. 检查是否被外部强制触发（service 或 REST）
        with self._force_lock:
            forced_prompt = self._force_pending
            forced = forced_prompt is not None
            self._force_pending = None

        # 3. 判定是否触发
        # 过滤掉低置信度 / 超量
        dets = dets[: self._max_dets]
        if not forced:
            if self._min_dets > 0 and len(dets) < self._min_dets:
                return
        decision = self._selector.decide(dets, force=forced)
        if not decision.fire:
            return

        # 4. 预处理 + 发起 VLM 推理
        small_bgr = downsample_keep_aspect(bgr, self._max_side)
        req = VLMRequest(
            frame_bgr=small_bgr,
            detections=dets,
            user_prompt=forced_prompt,
            system_prompt=self._system_prompt,
            crop_roi=False,
            frame_id=frame_id,
            timestamp=ts,
        )

        # 拿 provider 快照（锁内），随后释放锁再做真正的网络/模型推理，
        # 这样即便 describe 花几秒钟，也不会阻塞参数变更回调。
        with self._provider_lock:
            provider_ref = self._provider
            provider_name_snapshot = provider_ref.name

        self.get_logger().info(
            f"[VLM] 触发推理 reason={decision.reason} dets={len(dets)} "
            f"frame={frame_id} provider={provider_name_snapshot}"
        )

        t0 = time.time()
        try:
            resp = provider_ref.describe(req)
        except Exception as e:
            self.get_logger().error(f"[VLM] provider 异常: {e}")
            self._publish_status({"type": "error", "error": str(e)})
            return
        elapsed = (time.time() - t0) * 1000.0

        # 5. 发布场景描述
        out_payload = {
            "timestamp":   time.time(),
            "frame_id":    frame_id,
            "trigger":     decision.reason,
            "provider":    resp.provider or provider_ref.name,
            "model":       resp.model or provider_ref.model,
            "description": resp.description,
            "per_object":  resp.per_object,
            "elapsed_ms":  round(resp.elapsed_ms or elapsed, 1),
            "tokens_in":   resp.tokens_in,
            "tokens_out":  resp.tokens_out,
            "detections": [
                {
                    "class_id":   d.class_id,
                    "class_name": d.class_name,
                    "confidence": round(d.confidence, 3),
                    "bbox": {"x1": d.x1, "y1": d.y1, "x2": d.x2, "y2": d.y2},
                    "distance_m": d.distance_m,
                }
                for d in dets
            ],
        }
        out_msg = String()
        out_msg.data = json.dumps(out_payload, ensure_ascii=False)
        self._pub_desc.publish(out_msg)
        self._publish_status({
            "type": "infer_ok",
            "elapsed_ms": round(elapsed, 1),
            "provider": provider_ref.name,
            "trigger": decision.reason,
        })

    # ----------------------------------------------------------------------
    # 火警二次确认
    # ----------------------------------------------------------------------
    def _cb_fire_prealert(self, msg: String):
        """收到 /fire_smoke/prealert（fire_smoke_node 经过去抖动后发的预警）。

        说明：
        - 只记录 pending，不在回调里调 VLM（回调要尽快返回）；
        - 真正的 VLM 推理在 _tick_once 中进行（推理线程上下文）；
        - 冷却期内的新 prealert 也会被覆盖（保留最新一条）。
        """
        if not self._fire_enabled:
            return
        try:
            data = json.loads(msg.data)
        except Exception as e:
            self.get_logger().warn(f"[FIRE] prealert JSON 解析失败: {e}; raw={msg.data[:120]}")
            data = {"raw": msg.data}
        with self._fire_lock:
            self._fire_pending = data
        # 让后续即便有 keyframe cooldown 也不会影响这次火警调用
        if self._fire_force:
            self._selector.force_reset()
        self.get_logger().warn(
            f"[FIRE] 收到 prealert hits={data.get('hits')} boxes={len(data.get('boxes', []) or [])}"
        )

    def _consume_fire_pending(self) -> Optional[dict]:
        """取出 _fire_pending；冷却期内的请求直接丢弃，避免刷屏 / 烧 token。"""
        with self._fire_lock:
            data = self._fire_pending
            self._fire_pending = None
        if data is None:
            return None
        now = time.time()
        if now - self._last_fire_alert_ts < self._fire_cooldown:
            self.get_logger().info(
                f"[FIRE] 在冷却期内（剩余 "
                f"{self._fire_cooldown - (now - self._last_fire_alert_ts):.1f}s），丢弃 prealert"
            )
            return None
        return data

    def _run_fire_alert(self, bgr: np.ndarray, prealert: dict,
                        frame_id: int, ts: float) -> None:
        """对 prealert 做一次 VLM 二次确认，并把结构化结果发布到 /alert/fire。"""
        # 拿 provider 快照（锁内），后续网络调用不占锁
        with self._provider_lock:
            provider_ref = self._provider
            provider_ready = self._provider_ready
        if not provider_ready:
            self.get_logger().warn("[FIRE] provider 未就绪，跳过二次确认")
            return

        small_bgr = downsample_keep_aspect(bgr, self._max_side)
        # 用 prealert 自带的 fire/smoke 框做 detections 提示，VLM 看起来更有依据
        fake_dets: List[Detection] = []
        for b in (prealert.get("boxes") or [])[: self._max_dets]:
            try:
                fake_dets.append(Detection(
                    class_id=int(b.get("class_id", -1)),
                    class_name=str(b.get("class_name", "fire")),
                    confidence=float(b.get("confidence", 0.0)),
                    x1=float(b.get("x1", 0.0)),
                    y1=float(b.get("y1", 0.0)),
                    x2=float(b.get("x2", 0.0)),
                    y2=float(b.get("y2", 0.0)),
                    distance_m=float(b.get("distance_m", 0.0) or 0.0),
                ))
            except (TypeError, ValueError):
                continue

        req = VLMRequest(
            frame_bgr=small_bgr,
            detections=fake_dets,
            user_prompt=self._fire_prompt,     # 用严格 JSON 火警 prompt
            system_prompt=FIRE_SYSTEM_PROMPT,   # 覆盖通用导航 system prompt
            crop_roi=False,
            frame_id=frame_id,
            timestamp=ts,
            raw_prompt=True,                    # 关键：让 provider 不再追加导航话术
        )

        self.get_logger().warn(
            f"[FIRE] 调 VLM 二次确认 provider={provider_ref.name} "
            f"boxes={len(fake_dets)} frame={frame_id}"
        )
        t0 = time.time()
        try:
            resp = provider_ref.describe(req)
        except Exception as e:
            self.get_logger().error(f"[FIRE] VLM 异常: {e}")
            self._publish_status({"type": "fire_error", "error": str(e)})
            return
        elapsed = (time.time() - t0) * 1000.0

        parsed = self._parse_fire_json(resp.description or "")
        level = str(parsed.get("level", "low")).lower()
        if level not in ("none", "low", "high"):
            level = "low"

        out = {
            "timestamp":      time.time(),
            "frame_id":       frame_id,
            "level":          level,
            "fire_detected":  bool(parsed.get("fire_detected", False)),
            "smoke_detected": bool(parsed.get("smoke_detected", False)),
            "confidence":     float(parsed.get("confidence", 0.0) or 0.0),
            "reason":         str(parsed.get("reason", "") or ""),
            "recommendation": str(parsed.get("recommendation", "") or ""),
            "raw":            resp.description or "",
            "provider":       resp.provider or provider_ref.name,
            "model":          resp.model or provider_ref.model,
            "elapsed_ms":     round(resp.elapsed_ms or elapsed, 1),
            "prealert":       prealert,
        }
        if self._fire_with_image:
            try:
                ok, buf = cv2.imencode(".jpg", small_bgr,
                                       [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ok:
                    out["image_b64"] = base64.b64encode(buf.tobytes()).decode("ascii")
            except Exception as e:
                self.get_logger().warn(f"[FIRE] 图像 base64 编码失败: {e}")

        # 只有 level != none 才认为是“真火警”，更新冷却时间戳；
        # level == none 视为误报，仍然发出但不进冷却（让下次 prealert 还能继续核查）
        if level != "none":
            self._last_fire_alert_ts = time.time()

        msg = String()
        msg.data = json.dumps(out, ensure_ascii=False)
        self._pub_fire.publish(msg)

        self._publish_status({
            "type": "fire_alert",
            "level": level,
            "fire_detected": out["fire_detected"],
            "smoke_detected": out["smoke_detected"],
            "confidence": out["confidence"],
            "elapsed_ms": round(elapsed, 1),
        })
        self.get_logger().warn(
            f"[FIRE] 二次确认结果 level={level} fire={out['fire_detected']} "
            f"smoke={out['smoke_detected']} conf={out['confidence']:.2f} "
            f"elapsed={elapsed:.0f}ms reason={out['reason'][:60]}"
        )

    @staticmethod
    def _parse_fire_json(text: str) -> dict:
        """从 VLM 输出里抠出第一个 {...} JSON 对象；失败返回 {}。"""
        if not text:
            return {}
        # 先尝试直接 parse（最理想情况）
        try:
            return json.loads(text)
        except Exception:
            pass
        # 退化：用正则抓第一段花括号内容
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}

    # ----------------------------------------------------------------------
    # 工具
    # ----------------------------------------------------------------------
    def _publish_status(self, payload: dict):
        try:
            payload.setdefault("timestamp", time.time())
            msg = String()
            msg.data = json.dumps(payload, ensure_ascii=False)
            self._pub_status.publish(msg)
        except Exception:
            pass

    def request_force(self, user_prompt: Optional[str] = None):
        """外部调用入口（service / 后端 import 时使用）。"""
        with self._force_lock:
            self._force_pending = user_prompt or ""
        # 顺便重置触发器，避免被 cooldown 卡住
        self._selector.force_reset()

    # ----------------------------------------------------------------------
    # ROS Service
    # ----------------------------------------------------------------------
    def _srv_ask(self, request, response):
        """std_srvs/Trigger：不带参数的手动触发"""
        self.request_force(None)
        response.success = True
        response.message = "VLM 推理请求已排队"
        return response

    # ----------------------------------------------------------------------
    def destroy_node(self):
        self._stop_evt.set()
        try:
            self._thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            self._provider.close()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VLMSceneNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
