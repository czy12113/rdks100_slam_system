#!/usr/bin/env python3
"""
fire_smoke_node.py — D435i + YOLOv5（火/烟二分类）ROS2 节点
============================================================

订阅：
  /camera/camera/color/image_raw                          → RGB 帧
  /camera/camera/aligned_depth_to_color/image_raw         → 深度帧（可选，仅用于估距）

发布：
  /fire_smoke/results            std_msgs/String          → JSON 检测结果
  /fire_smoke/annotated_image    sensor_msgs/Image        → 带红框 + 距离标注（BGR8）
  /fire_smoke/prealert           std_msgs/String          → "预警"信号
                                                            连续 N 帧命中后触发一次
                                                            由 vlm_scene 节点订阅做二次确认

为什么独立于 detection_node_bpu.py：
  - 通用 COCO 80 类检测跑在 BPU 上，火/烟模型是另一份权重，必须并列。
  - 火/烟模型走 CPU torch 推理：30+ FPS 不需要，3~10 FPS 已足够告警。
  - 出问题时降级容易，不影响主导航避障管线。

设计要点：
  - 双缓冲：spin 线程只写最新帧，推理线程独立消费，永不阻塞 DDS。
  - "去抖"：必须连续 N 帧检出火/烟才触发 prealert（默认 3 帧），抑制单帧误报。
  - "冷却"：prealert 触发后 X 秒内不再触发（默认 10s），避免刷屏。
  - 兼容性 patch：和 detection_node.py 完全一致（aarch64 上跳过 fuse()、关掉 inplace）。

模型路径默认：
  <package_share>/weights/fire_smoke_best.pt
  也可以通过 ros2 launch ... weights_path:=/abs/path 覆盖。
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import threading
from collections import deque
from typing import List, Optional

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String


# ──────────────────────────────────────────────────────────────────────────────
# 类别名（与 fire_smoke.yaml: names: ['fire', 'smoke'] 对齐）
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_CLASS_NAMES = ["fire", "smoke"]

# 框颜色（BGR）：fire=红，smoke=橙
CLASS_COLORS_BGR = {
    "fire":  (0,   0, 255),   # 红
    "smoke": (0, 165, 255),   # 橙
}


# ──────────────────────────────────────────────────────────────────────────────
# NMS（与 detection_node.py 完全相同的算法，但只针对 2 类）
# ──────────────────────────────────────────────────────────────────────────────
def apply_nms(raw_pred, conf_thresh: float, iou_thresh: float,
              max_det: int, num_classes: int):
    """对 YOLOv5 原始输出做 obj_conf * cls_conf 过滤 + 类内 NMS"""
    import torch
    try:
        from torchvision.ops import nms as torchvision_nms
        _has_tv_nms = True
    except ImportError:
        _has_tv_nms = False

    if isinstance(raw_pred, (tuple, list)):
        pred = raw_pred[0]
    else:
        pred = raw_pred
    if pred.dim() == 3:
        pred = pred[0]
    pred = pred.cpu().float()

    obj_conf = pred[:, 4]
    cls_scores = pred[:, 5: 5 + num_classes]
    cls_conf, cls_ids = cls_scores.max(dim=1)
    score = obj_conf * cls_conf

    mask = score >= conf_thresh
    pred = pred[mask]
    score = score[mask]
    cls_ids = cls_ids[mask]
    if pred.shape[0] == 0:
        return []

    cx, cy, bw, bh = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    boxes = torch.stack([cx - bw / 2, cy - bh / 2,
                         cx + bw / 2, cy + bh / 2], dim=1)

    results = []
    for c in cls_ids.unique():
        m = cls_ids == c
        bx = boxes[m]
        sc = score[m]
        ids = m.nonzero(as_tuple=True)[0]
        if _has_tv_nms:
            keep = torchvision_nms(bx, sc, iou_thresh)
        else:
            keep = _greedy_nms(bx, sc, iou_thresh)
        for k in keep[:max_det]:
            i = ids[k].item()
            results.append([
                float(boxes[i, 0]), float(boxes[i, 1]),
                float(boxes[i, 2]), float(boxes[i, 3]),
                float(score[i]), int(cls_ids[i]),
            ])
    results.sort(key=lambda r: r[4], reverse=True)
    return results[:max_det]


def _greedy_nms(boxes, scores, iou_thresh: float):
    import torch
    order = scores.argsort(descending=True)
    keep = []
    while order.numel() > 0:
        i = order[0].item()
        keep.append(i)
        if order.numel() == 1:
            break
        rest = order[1:]
        b = boxes[i]; rb = boxes[rest]
        ix1 = torch.max(b[0], rb[:, 0]); iy1 = torch.max(b[1], rb[:, 1])
        ix2 = torch.min(b[2], rb[:, 2]); iy2 = torch.min(b[3], rb[:, 3])
        iw = (ix2 - ix1).clamp(0); ih = (iy2 - iy1).clamp(0)
        inter = iw * ih
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        area_r = (rb[:, 2] - rb[:, 0]) * (rb[:, 3] - rb[:, 1])
        iou = inter / (area_b + area_r - inter + 1e-6)
        order = rest[iou <= iou_thresh]
    return torch.tensor(keep, dtype=torch.long)


# ──────────────────────────────────────────────────────────────────────────────
# 深度测距（同 detection_node.py）
# ──────────────────────────────────────────────────────────────────────────────
def get_mid_pos_distance(box, depth_data: np.ndarray, randnum: int = 24) -> float:
    if depth_data is None:
        return 0.0
    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    mid_x = (x1 + x2) // 2
    mid_y = (y1 + y2) // 2
    min_val = max(1, min(abs(x2 - x1), abs(y2 - y1)))
    h, w = depth_data.shape
    vals = []
    for _ in range(randnum):
        bias = random.randint(-min_val // 4, min_val // 4)
        px = max(0, min(w - 1, mid_x + bias))
        py = max(0, min(h - 1, mid_y + bias))
        v = int(depth_data[py, px])
        if v > 0:
            vals.append(v)
    if not vals:
        return 0.0
    arr = np.sort(np.array(vals))
    q1 = len(arr) // 4
    q3 = len(arr) * 3 // 4
    filtered = arr[q1:q3] if q3 > q1 else arr
    return float(np.mean(filtered))


# ──────────────────────────────────────────────────────────────────────────────
# 主节点
# ──────────────────────────────────────────────────────────────────────────────
class FireSmokeNode(Node):
    """火/烟检测节点（CPU YOLOv5 + 去抖 prealert）"""

    def __init__(self):
        super().__init__("fire_smoke_detection_node")

        # ─── 参数 ──────────────────────────────────────────────────────────
        # 模型文件路径。默认指向 d435i_detection/weights/fire_smoke_best.pt
        # （在 setup.py 的 data_files 里没有把 weights/ 装到 share/ 目录，
        # 所以这里默认值用源码绝对路径；推荐通过 launch 参数显式传入。）
        self.declare_parameter("weights_path",
            "/home/sunrise/rdks100_slam/ros2_ws/src/d435i_detection/weights/fire_smoke_best.pt")
        # 把 fire-smoke-detect 的 yolov5 源码目录加到 sys.path，
        # 让 torch.load 能找到自定义模块（与 detection_node.py 同样套路）。
        self.declare_parameter("yolov5_src_dir",
            "/home/sunrise/rdks100_slam/fire-smoke-detect-yolov5/yolov5")

        # 二分类
        self.declare_parameter("class_names", DEFAULT_CLASS_NAMES)
        # 置信度阈值。fire/smoke 模型本身比 COCO 噪点更大，
        # 建议从 0.45 起步，看到误报多就调到 0.5 ~ 0.6。
        self.declare_parameter("confidence_threshold", 0.45)
        # NMS IoU
        self.declare_parameter("iou_threshold", 0.45)
        # 每帧最多保留几个框
        self.declare_parameter("max_detections", 10)
        # 推理分辨率：火/烟模型默认 640，CPU 上 640 会比较吃力，
        # 这里默认降到 416，明显加速且基本不损失火焰大目标的识别率。
        self.declare_parameter("infer_width", 416)
        self.declare_parameter("infer_height", 416)

        # 深度测距
        self.declare_parameter("depth_sample_count", 24)
        # 推理节流：火警不需要 30fps，2~5fps 完全够，省 CPU
        self.declare_parameter("infer_interval_sec", 0.20)

        # 去抖：必须连续 N 个推理周期都命中才发 prealert
        self.declare_parameter("consecutive_hits", 3)
        # prealert 冷却：触发后 X 秒内不再发 prealert
        self.declare_parameter("prealert_cooldown_sec", 10.0)
        # 只有 fire 命中才算"高危"，smoke 命中只算"中危"
        # 这里只发布信号，等级判定在 vlm_node 中做（让大模型来定）

        # 订阅 / 发布 topic
        self.declare_parameter("sub_topic_rgb",
                                "/camera/camera/color/image_raw")
        self.declare_parameter("sub_topic_depth",
                                "/camera/camera/aligned_depth_to_color/image_raw")
        self.declare_parameter("pub_topic_results",   "/fire_smoke/results")
        self.declare_parameter("pub_topic_annotated", "/fire_smoke/annotated_image")
        self.declare_parameter("pub_topic_prealert",  "/fire_smoke/prealert")
        # 是否发布带标注图（关掉省 CPU）
        self.declare_parameter("publish_annotated", True)
        # 是否订阅 depth（D435i 不可用或对齐失败时关掉，避免无谓警告）
        self.declare_parameter("use_depth", True)

        # ─── 读取参数 ──────────────────────────────────────────────────────
        self._weights_path = self.get_parameter("weights_path").value
        self._yolov5_src   = self.get_parameter("yolov5_src_dir").value
        self._class_names: List[str] = list(self.get_parameter("class_names").value) \
                                       or DEFAULT_CLASS_NAMES
        self._conf_thresh = float(self.get_parameter("confidence_threshold").value)
        self._iou_thresh  = float(self.get_parameter("iou_threshold").value)
        self._max_det     = int(self.get_parameter("max_detections").value)
        self._infer_w     = int(self.get_parameter("infer_width").value)
        self._infer_h     = int(self.get_parameter("infer_height").value)
        self._sample_cnt  = int(self.get_parameter("depth_sample_count").value)
        self._infer_intv  = float(self.get_parameter("infer_interval_sec").value)
        self._consec_hits = int(self.get_parameter("consecutive_hits").value)
        self._pre_cooldown = float(self.get_parameter("prealert_cooldown_sec").value)
        self._sub_rgb      = self.get_parameter("sub_topic_rgb").value
        self._sub_depth    = self.get_parameter("sub_topic_depth").value
        self._pub_results  = self.get_parameter("pub_topic_results").value
        self._pub_anno     = self.get_parameter("pub_topic_annotated").value
        self._pub_prealert = self.get_parameter("pub_topic_prealert").value
        self._pub_annotated = bool(self.get_parameter("publish_annotated").value)
        self._use_depth     = bool(self.get_parameter("use_depth").value)

        # ─── 双缓冲 ────────────────────────────────────────────────────────
        self._buf_lock      = threading.Lock()
        self._latest_rgb:   Optional[np.ndarray] = None
        self._latest_depth: Optional[np.ndarray] = None
        self._latest_rgb_ts: float = 0.0

        # ─── 模型 ──────────────────────────────────────────────────────────
        self._model = None
        self._model_loaded = False

        # ─── 去抖状态 ──────────────────────────────────────────────────────
        # 最近 N 次推理是否有 fire/smoke 命中（True/False）
        self._recent_hits: deque[bool] = deque(maxlen=max(1, self._consec_hits))
        self._last_prealert_ts = 0.0

        # ─── QoS ───────────────────────────────────────────────────────────
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )

        # ─── 订阅 ──────────────────────────────────────────────────────────
        self.create_subscription(Image, self._sub_rgb, self._cb_rgb, sensor_qos)
        if self._use_depth:
            self.create_subscription(Image, self._sub_depth, self._cb_depth, sensor_qos)

        # ─── 发布 ──────────────────────────────────────────────────────────
        self._pub_res = self.create_publisher(String, self._pub_results, 10)
        self._pub_anno_node = (
            self.create_publisher(Image, self._pub_anno, 10)
            if self._pub_annotated else None
        )
        self._pub_pre = self.create_publisher(String, self._pub_prealert, 10)

        # ─── 推理线程 ──────────────────────────────────────────────────────
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._infer_loop, daemon=True, name="fire_smoke_infer")
        self._thread.start()

        self.get_logger().info(
            "[FireSmoke] 已启动\n"
            f"  weights        : {self._weights_path}\n"
            f"  yolov5_src_dir : {self._yolov5_src}\n"
            f"  classes        : {self._class_names}\n"
            f"  conf / iou     : {self._conf_thresh} / {self._iou_thresh}\n"
            f"  infer size     : {self._infer_w}x{self._infer_h}\n"
            f"  infer interval : {self._infer_intv}s\n"
            f"  consec hits    : {self._consec_hits}\n"
            f"  prealert cool  : {self._pre_cooldown}s\n"
            f"  sub_rgb        : {self._sub_rgb}\n"
            f"  sub_depth      : {self._sub_depth} (use={self._use_depth})\n"
            f"  pub_results    : {self._pub_results}\n"
            f"  pub_annotated  : {self._pub_anno} (enable={self._pub_annotated})\n"
            f"  pub_prealert   : {self._pub_prealert}"
        )

    # ──────────────────────────────────────────────────────────────────────
    # 回调（spin 线程，必须很快）
    # ──────────────────────────────────────────────────────────────────────
    def _cb_rgb(self, msg: Image):
        try:
            arr = np.frombuffer(msg.data, np.uint8)
            enc = msg.encoding.lower()
            if "rgb" in enc:
                img = arr.reshape((msg.height, msg.width, 3))[..., ::-1].copy()
            else:
                img = arr.reshape((msg.height, msg.width, 3)).copy()
            ts = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            with self._buf_lock:
                self._latest_rgb = img
                self._latest_rgb_ts = ts
        except Exception as e:
            self.get_logger().error(f"[FireSmoke] RGB cb fail: {e}")

    def _cb_depth(self, msg: Image):
        try:
            arr = np.frombuffer(msg.data, np.uint16)
            d = arr.reshape((msg.height, msg.width)).copy()
            with self._buf_lock:
                self._latest_depth = d
        except Exception as e:
            self.get_logger().error(f"[FireSmoke] Depth cb fail: {e}")

    # ──────────────────────────────────────────────────────────────────────
    # 模型加载（懒加载，在推理线程内）
    # ──────────────────────────────────────────────────────────────────────
    def _load_model(self):
        try:
            import torch
            self.get_logger().info(f"[FireSmoke] 加载模型: {self._weights_path}")
            if self._yolov5_src and self._yolov5_src not in sys.path:
                sys.path.insert(0, self._yolov5_src)

            ckpt = torch.load(self._weights_path, map_location="cpu")
            model = ckpt["model"].float().eval()
            # aarch64 兼容
            for m in model.modules():
                if hasattr(m, "inplace"):
                    m.inplace = False
                if isinstance(m, torch.nn.Upsample):
                    m.recompute_scale_factor = None
            self._model = model

            # 类别名优先读模型自带
            try:
                names = ckpt.get("names") or (
                    model.module.names if hasattr(model, "module") else model.names
                )
                if names:
                    self._class_names = (
                        list(names.values()) if isinstance(names, dict) else list(names)
                    )
            except Exception:
                pass

            self._model_loaded = True
            self.get_logger().info(
                f"[FireSmoke] 模型加载成功 | 类别={self._class_names}"
            )
        except Exception as e:
            self.get_logger().error(f"[FireSmoke] 模型加载失败: {e}")
            self._model_loaded = False

    # ──────────────────────────────────────────────────────────────────────
    # 推理主循环
    # ──────────────────────────────────────────────────────────────────────
    def _infer_loop(self):
        import cv2
        import torch

        self._load_model()
        if not self._model_loaded:
            self.get_logger().error("[FireSmoke] 模型未就绪，线程退出")
            return

        frame_id = 0
        last_log = 0.0
        last_infer = 0.0

        while rclpy.ok() and not self._stop.is_set():
            now = time.time()
            # 节流
            if now - last_infer < self._infer_intv:
                time.sleep(0.01)
                continue
            last_infer = now

            with self._buf_lock:
                rgb = self._latest_rgb
                depth = self._latest_depth if self._use_depth else None
                rgb_ts = self._latest_rgb_ts
            if rgb is None:
                time.sleep(0.05)
                continue

            # ─ 预处理 ───────────────────────────────────────────────────
            if self._infer_w > 0 and self._infer_h > 0:
                infer_img = cv2.resize(rgb, (self._infer_w, self._infer_h),
                                       interpolation=cv2.INTER_LINEAR)
            else:
                infer_img = rgb

            try:
                t0 = time.time()
                img_rgb = infer_img[..., ::-1].copy()
                chw = img_rgb.transpose(2, 0, 1)
                tensor = torch.from_numpy(chw).float() / 255.0
                tensor = tensor.unsqueeze(0)
                with torch.no_grad():
                    raw = self._model(tensor)
                infer_ms = (time.time() - t0) * 1000.0
            except Exception as e:
                self.get_logger().error(f"[FireSmoke] 推理失败: {e}")
                time.sleep(0.2)
                continue

            # ─ NMS ──────────────────────────────────────────────────────
            res = apply_nms(raw, self._conf_thresh, self._iou_thresh,
                            self._max_det, num_classes=len(self._class_names))

            # ─ 坐标缩放回原图 ────────────────────────────────────────────
            h_orig, w_orig = rgb.shape[:2]
            sx = w_orig / float(infer_img.shape[1])
            sy = h_orig / float(infer_img.shape[0])

            dets = []
            anno = rgb.copy() if (self._pub_annotated and self._pub_anno_node) else None
            has_fire = False
            has_smoke = False

            for row in res:
                x1, y1, x2, y2, conf, cid = row
                x1, x2 = x1 * sx, x2 * sx
                y1, y2 = y1 * sy, y2 * sy
                x1 = max(0.0, min(float(w_orig), x1))
                y1 = max(0.0, min(float(h_orig), y1))
                x2 = max(0.0, min(float(w_orig), x2))
                y2 = max(0.0, min(float(h_orig), y2))
                cname = (self._class_names[cid]
                         if 0 <= cid < len(self._class_names) else str(cid))
                if cname == "fire":
                    has_fire = True
                elif cname == "smoke":
                    has_smoke = True

                dist_mm = get_mid_pos_distance([x1, y1, x2, y2],
                                               depth, self._sample_cnt)
                dist_m = dist_mm / 1000.0
                dets.append({
                    "class_id":   int(cid),
                    "class_name": cname,
                    "confidence": round(float(conf), 3),
                    "bbox": {"x1": round(x1, 1), "y1": round(y1, 1),
                             "x2": round(x2, 1), "y2": round(y2, 1)},
                    "distance_m": round(dist_m, 3),
                })

                if anno is not None:
                    color = CLASS_COLORS_BGR.get(cname, (0, 0, 255))
                    cv2.rectangle(anno, (int(x1), int(y1)), (int(x2), int(y2)),
                                  color, 2)
                    label = f"{cname} {conf:.2f}"
                    if dist_m > 0:
                        label += f" {dist_m:.2f}m"
                    (tw, th), _ = cv2.getTextSize(label,
                                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                    ty = max(int(y1) - 4, th + 2)
                    cv2.rectangle(anno, (int(x1), ty - th - 2),
                                  (int(x1) + tw + 2, ty + 2), color, -1)
                    cv2.putText(anno, label, (int(x1) + 1, ty),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

            frame_id += 1

            # ─ 发布检测结果 ──────────────────────────────────────────────
            payload = {
                "timestamp":  rgb_ts,
                "frame_id":   frame_id,
                "infer_ms":   round(infer_ms, 1),
                "count":      len(dets),
                "has_fire":   has_fire,
                "has_smoke":  has_smoke,
                "detections": dets,
            }
            msg = String()
            msg.data = json.dumps(payload, ensure_ascii=False)
            self._pub_res.publish(msg)

            # ─ 发布标注图像 ──────────────────────────────────────────────
            if anno is not None:
                a = Image()
                a.header.stamp = self.get_clock().now().to_msg()
                a.header.frame_id = "camera_color_optical_frame"
                a.height = anno.shape[0]
                a.width = anno.shape[1]
                a.encoding = "bgr8"
                a.step = anno.shape[1] * 3
                a.data = anno.tobytes()
                self._pub_anno_node.publish(a)

            # ─ 去抖 + 预警 ───────────────────────────────────────────────
            self._recent_hits.append(has_fire or has_smoke)
            consec_all_hit = (
                len(self._recent_hits) >= self._consec_hits
                and all(self._recent_hits)
            )
            if consec_all_hit and (now - self._last_prealert_ts) >= self._pre_cooldown:
                self._last_prealert_ts = now
                pre_payload = {
                    "timestamp":  now,
                    "frame_id":   frame_id,
                    "has_fire":   has_fire,
                    "has_smoke":  has_smoke,
                    "consec":     int(self._consec_hits),
                    # 给 vlm_node 一份精简检测摘要
                    "detections": dets,
                }
                pre_msg = String()
                pre_msg.data = json.dumps(pre_payload, ensure_ascii=False)
                self._pub_pre.publish(pre_msg)
                self.get_logger().warn(
                    f"[FireSmoke] *** PREALERT *** fire={has_fire} smoke={has_smoke} "
                    f"frame={frame_id}（已发布 /fire_smoke/prealert，等待 VLM 二次确认）"
                )
                # 清空近期窗口，避免下一帧又立刻命中
                self._recent_hits.clear()

            # ─ 周期诊断日志 ──────────────────────────────────────────────
            if now - last_log >= 5.0:
                self.get_logger().info(
                    f"[FireSmoke] frame={frame_id} infer={infer_ms:.1f}ms "
                    f"dets={len(dets)} fire={has_fire} smoke={has_smoke}"
                )
                last_log = now


def main(args=None):
    rclpy.init(args=args)
    node = FireSmokeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._stop.set()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
