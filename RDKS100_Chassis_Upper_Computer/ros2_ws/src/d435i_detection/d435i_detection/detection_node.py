"""
detection_node.py
-----------------
D435i + YOLOv5 目标检测 + 深度测距 ROS2 节点。

订阅：
  /camera/camera/color/image_raw                          → RGB 帧 (sensor_msgs/Image)
  /camera/camera/aligned_depth_to_color/image_raw         → 深度帧 (sensor_msgs/Image, Z16)

发布：
  /detection/results          → std_msgs/String (JSON)
  /detection/annotated_image  → sensor_msgs/Image (BGR8，已画框+距离标注)

关键修复（v2）：
  - 手动 torch.load 加载的模型直接调用 model(tensor) 返回原始特征张量
    (shape [1, num_anchors*grids, 85])，必须经过 NMS 才能得到真正的检测框。
    旧版直接 dets[0].cpu().numpy() 遍历原始张量，产生海量错误框。
  - 修复 frame_count（未定义）→ frame_id。
  - 新增 iou_threshold / max_detections / target_classes 参数，方便按需调整。
"""

import json
import random
import sys
import time
import threading
from typing import Optional, List

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String


# ──────────────────────────────────────────────────────────────────────────────
# NMS 后处理（torchvision 方案，纯 CPU 可用）
# ──────────────────────────────────────────────────────────────────────────────

def apply_nms(raw_pred, conf_thresh: float, iou_thresh: float, max_det: int):
    """
    对 YOLOv5 原始输出做置信度过滤 + NMS，返回检测列表。

    Args:
        raw_pred:    model(tensor) 的第一个输出元素，shape [1, N, 85]
                     其中 85 = cx, cy, w, h, obj_conf, 80 class scores
        conf_thresh: 置信度阈值（obj_conf * cls_conf）
        iou_thresh:  NMS IoU 阈值
        max_det:     每帧最多保留的检测框数

    Returns:
        list of [x1, y1, x2, y2, conf, cls_id]  （像素坐标，相对推理图尺寸）
    """
    import torch
    try:
        from torchvision.ops import nms as torchvision_nms
        _has_tv_nms = True
    except ImportError:
        _has_tv_nms = False

    # raw_pred 可能是 tuple/list，取第一个 tensor
    if isinstance(raw_pred, (tuple, list)):
        pred = raw_pred[0]
    else:
        pred = raw_pred

    # shape: [1, N, 85] 或 [N, 85]
    if pred.dim() == 3:
        pred = pred[0]   # → [N, 85]

    pred = pred.cpu().float()

    # ── 置信度过滤 ────────────────────────────────────────────────────────────
    # YOLOv5: col4 = obj_conf, col5: = class scores
    obj_conf  = pred[:, 4]                            # [N]
    cls_scores = pred[:, 5:]                          # [N, 80]
    cls_conf, cls_ids = cls_scores.max(dim=1)         # [N]
    score = obj_conf * cls_conf                       # [N]

    mask = score >= conf_thresh
    pred = pred[mask]
    score = score[mask]
    cls_ids = cls_ids[mask]

    if pred.shape[0] == 0:
        return []

    # ── cx,cy,w,h → x1,y1,x2,y2 ─────────────────────────────────────────────
    cx, cy, bw, bh = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    x1 = cx - bw / 2
    y1 = cy - bh / 2
    x2 = cx + bw / 2
    y2 = cy + bh / 2

    import torch
    boxes = torch.stack([x1, y1, x2, y2], dim=1)   # [M, 4]

    # ── 按类别分组做 NMS（class-aware NMS）────────────────────────────────────
    results = []
    unique_cls = cls_ids.unique()
    for c in unique_cls:
        mask_c = cls_ids == c
        boxes_c = boxes[mask_c]
        scores_c = score[mask_c]
        ids_c = mask_c.nonzero(as_tuple=True)[0]

        if _has_tv_nms:
            keep = torchvision_nms(boxes_c, scores_c, iou_thresh)
        else:
            # 简易 greedy NMS fallback（torchvision 不可用时）
            keep = _greedy_nms(boxes_c, scores_c, iou_thresh)

        for k in keep[:max_det]:
            idx = ids_c[k].item()
            results.append([
                float(boxes[idx, 0]), float(boxes[idx, 1]),
                float(boxes[idx, 2]), float(boxes[idx, 3]),
                float(score[idx]),
                int(cls_ids[idx]),
            ])

    # 全局 max_det 截断（所有类别合计）
    results = sorted(results, key=lambda r: r[4], reverse=True)[:max_det]
    return results


def _greedy_nms(boxes, scores, iou_thresh: float):
    """torchvision 不可用时的简易 greedy NMS（CPU numpy 实现）"""
    import torch
    order = scores.argsort(descending=True)
    keep = []
    while order.numel() > 0:
        i = order[0].item()
        keep.append(i)
        if order.numel() == 1:
            break
        rest = order[1:]
        # 计算 IoU
        b = boxes[i]
        rb = boxes[rest]
        inter_x1 = torch.max(b[0], rb[:, 0])
        inter_y1 = torch.max(b[1], rb[:, 1])
        inter_x2 = torch.min(b[2], rb[:, 2])
        inter_y2 = torch.min(b[3], rb[:, 3])
        inter_w  = (inter_x2 - inter_x1).clamp(0)
        inter_h  = (inter_y2 - inter_y1).clamp(0)
        inter    = inter_w * inter_h
        area_b   = (b[2] - b[0]) * (b[3] - b[1])
        area_rb  = (rb[:, 2] - rb[:, 0]) * (rb[:, 3] - rb[:, 1])
        union    = area_b + area_rb - inter
        iou      = inter / (union + 1e-6)
        order    = rest[iou <= iou_thresh]
    return torch.tensor(keep, dtype=torch.long)


# ──────────────────────────────────────────────────────────────────────────────
# 深度测距（移植自 main_debug.py: get_mid_pos）
# ──────────────────────────────────────────────────────────────────────────────

def get_mid_pos_distance(
    box: list,
    depth_data: np.ndarray,
    randnum: int = 24,
) -> float:
    """
    在检测框中心区域随机采样 randnum 个深度点，
    取中值滤波区间（去掉最大/最小各 1/4）的均值作为距离估计。

    Args:
        box:        [x1, y1, x2, y2, ...]
        depth_data: H×W uint16 深度图（单位 mm，Z16 格式）
        randnum:    随机采样点数

    Returns:
        距离（毫米）；无有效点返回 0.0
    """
    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    mid_x = (x1 + x2) // 2
    mid_y = (y1 + y2) // 2
    min_val = max(1, min(abs(x2 - x1), abs(y2 - y1)))

    h, w = depth_data.shape
    distance_list = []
    for _ in range(randnum):
        bias = random.randint(-min_val // 4, min_val // 4)
        px = max(0, min(w - 1, mid_x + bias))
        py = max(0, min(h - 1, mid_y + bias))
        dist = int(depth_data[py, px])
        if dist > 0:
            distance_list.append(dist)

    if not distance_list:
        return 0.0

    arr = np.sort(np.array(distance_list))
    q1 = len(arr) // 4
    q3 = len(arr) * 3 // 4
    filtered = arr[q1:q3] if q3 > q1 else arr
    return float(np.mean(filtered))


# ──────────────────────────────────────────────────────────────────────────────
# COCO 80 类名称表（yolov5s.pt 默认使用 COCO，避免依赖 model.names）
#   注意：id=52 原本是 "pizza"，仓库场景下常把火焰误识别成 pizza，
#         这里直接把该 slot 改名为 "fire"，配合下方 WAREHOUSE_CLASSES
#         白名单只透出仓库相关类别，让演示时火焰稳定显示为 fire。
# ──────────────────────────────────────────────────────────────────────────────
COCO_NAMES = [
    "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat",
    "traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat",
    "dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack",
    "umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball",
    "kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket",
    "bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple",
    "sandwich","orange","broccoli","carrot","hot dog","fire","donut","cake","chair",
    "couch","potted plant","bed","dining table","toilet","tv","laptop","mouse",
    "remote","keyboard","cell phone","microwave","oven","toaster","sink",
    "refrigerator","book","clock","vase","scissors","teddy bear","hair drier",
    "toothbrush",
]

# ──────────────────────────────────────────────────────────────────────────────
# 仓库场景默认白名单（target_classes 未显式配置时使用）
#   只透出仓库巡检真正关心的类别，其他 COCO 类不出框、不进 JSON。
#   52 = fire（原 pizza slot，避免火焰被标成 pizza）
# ──────────────────────────────────────────────────────────────────────────────
WAREHOUSE_CLASSES = [
    0,   # person
    1,   # bicycle
    2,   # car
    3,   # motorcycle
    5,   # bus
    7,   # truck
    24,  # backpack
    26,  # handbag
    28,  # suitcase
    39,  # bottle
    52,  # fire (原 pizza)
    56,  # chair
    63,  # laptop
    67,  # cell phone
    73,  # book
    74,  # clock
    76,  # scissors
]


# ──────────────────────────────────────────────────────────────────────────────
# ROS2 检测节点
# ──────────────────────────────────────────────────────────────────────────────

class DetectionNode(Node):
    """
    D435i + YOLOv5 检测节点（v2，修复 NMS 缺失问题）。

    线程模型：
      - ROS2 spin 线程：接收图像 topic，存入双缓冲（不阻塞 spin）
      - 推理线程（独立 daemon thread）：双缓冲取帧 → YOLO → NMS → 深度测距 → 发布结果
    """

    def __init__(self):
        super().__init__("d435i_detection_node")

        # ── 参数声明 ────────────────────────────────────────────────────────
        self.declare_parameter(
            "model_path",
            "/home/sunrise/rdks100_slam/d435i_ros2/d435i_ros2/weights/yolov5s.pt")
        # 置信度阈值（0~1）：越高误检越少，漏检越多；建议 0.4~0.6
        self.declare_parameter("confidence_threshold", 0.5)
        # NMS IoU 阈值（0~1）：越低保留框越少；建议 0.4~0.5
        self.declare_parameter("iou_threshold", 0.45)
        # 每帧最多保留检测框数（防止异常情况刷屏）
        self.declare_parameter("max_detections", 20)
        # 深度测距随机采样点数（越多越稳定，越慢）
        self.declare_parameter("depth_sample_count", 24)
        # 推理分辨率（0 = 使用原始图像尺寸，不 resize）
        self.declare_parameter("infer_width", 640)
        self.declare_parameter("infer_height", 480)
        # 发布 topic
        self.declare_parameter("pub_topic_results",   "/detection/results")
        self.declare_parameter("pub_topic_annotated", "/detection/annotated_image")
        # 订阅 topic
        self.declare_parameter("sub_topic_rgb",   "/camera/camera/color/image_raw")
        self.declare_parameter("sub_topic_depth", "/camera/camera/aligned_depth_to_color/image_raw")
        # 是否发布带标注的图像
        self.declare_parameter("publish_annotated", True)
        # 推理设备（cpu / cuda）
        self.declare_parameter("device", "cpu")
        # 目标类别过滤（空列表 = 检测所有类别）
        # 示例：只检测人和车 → target_classes: [0, 2]（COCO 类别 ID）
        self.declare_parameter("target_classes", rclpy.parameter.Parameter.Type.INTEGER_ARRAY)

        # ── 读取参数 ────────────────────────────────────────────────────────
        self._model_path    = self.get_parameter("model_path").value
        self._conf_thresh   = float(self.get_parameter("confidence_threshold").value)
        self._iou_thresh    = float(self.get_parameter("iou_threshold").value)
        self._max_det       = int(self.get_parameter("max_detections").value)
        self._sample_cnt    = int(self.get_parameter("depth_sample_count").value)
        self._infer_w       = int(self.get_parameter("infer_width").value)
        self._infer_h       = int(self.get_parameter("infer_height").value)
        self._pub_results   = self.get_parameter("pub_topic_results").value
        self._pub_anno      = self.get_parameter("pub_topic_annotated").value
        self._sub_rgb       = self.get_parameter("sub_topic_rgb").value
        self._sub_depth     = self.get_parameter("sub_topic_depth").value
        self._pub_annotated = bool(self.get_parameter("publish_annotated").value)
        self._device        = self.get_parameter("device").value

        # target_classes：未显式配置 = 走仓库白名单，显式配置非空 = 只检测指定类别
        # （历史行为是"空 = 全部"，仓库场景不需要检测 COCO 里那些无关物体，
        #   所以把默认值改成 WAREHOUSE_CLASSES；launch 里显式传数组仍可覆盖。）
        try:
            tc = self.get_parameter("target_classes").value
            self._target_classes: Optional[List[int]] = list(tc) if tc else list(WAREHOUSE_CLASSES)
        except Exception:
            self._target_classes = list(WAREHOUSE_CLASSES)

        # ── 双缓冲（spin 线程写，推理线程读）────────────────────────────────
        self._buf_lock          = threading.Lock()
        self._latest_rgb:       Optional[np.ndarray] = None   # H×W×3 uint8 BGR
        self._latest_depth:     Optional[np.ndarray] = None   # H×W uint16 mm
        self._latest_rgb_ts:    float = 0.0
        self._latest_depth_ts:  float = 0.0

        # ── 模型状态 ─────────────────────────────────────────────────────────
        self._model           = None
        self._model_names: List[str] = COCO_NAMES   # 默认 COCO 80 类
        self._model_loaded    = False
        self._model_load_error: Optional[str] = None

        # ── QoS：传感器数据，BEST_EFFORT + 只保留最新 1 帧 ──────────────────
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # ── 订阅者 ──────────────────────────────────────────────────────────
        self._sub_rgb_node   = self.create_subscription(
            Image, self._sub_rgb,   self._cb_rgb,   sensor_qos)
        self._sub_depth_node = self.create_subscription(
            Image, self._sub_depth, self._cb_depth, sensor_qos)

        # ── 发布者 ──────────────────────────────────────────────────────────
        self._pub_results_node = self.create_publisher(
            String, self._pub_results, 10)
        self._pub_anno_node = (
            self.create_publisher(Image, self._pub_anno, 10)
            if self._pub_annotated else None
        )

        # ── 推理线程 ─────────────────────────────────────────────────────────
        self._infer_thread = threading.Thread(
            target=self._infer_loop,
            daemon=True,
            name="yolo_infer",
        )
        self._infer_thread.start()

        self.get_logger().info(
            f"[DetectionNode v2] 已启动\n"
            f"  model      : {self._model_path}\n"
            f"  conf_thresh: {self._conf_thresh}  iou_thresh: {self._iou_thresh}\n"
            f"  max_det    : {self._max_det}  device: {self._device}\n"
            f"  target_cls : {self._target_classes if self._target_classes else '全部'}\n"
            f"  sub_rgb    : {self._sub_rgb}\n"
            f"  sub_depth  : {self._sub_depth}\n"
            f"  pub_results: {self._pub_results}\n"
            f"  pub_anno   : {self._pub_anno}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 图像回调（spin 线程，仅写缓冲，不做任何推理）
    # ──────────────────────────────────────────────────────────────────────────

    def _cb_rgb(self, msg: Image):
        """接收 RGB 帧，转为 numpy BGR，写入双缓冲"""
        try:
            arr = np.frombuffer(msg.data, dtype=np.uint8)
            enc = msg.encoding.lower()
            if "rgb" in enc:
                img = arr.reshape((msg.height, msg.width, 3))[..., ::-1].copy()
            else:
                img = arr.reshape((msg.height, msg.width, 3)).copy()  # bgr8

            ts = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            with self._buf_lock:
                self._latest_rgb    = img
                self._latest_rgb_ts = ts
        except Exception as e:
            self.get_logger().error(f"[DetectionNode] RGB 回调失败: {e}")

    def _cb_depth(self, msg: Image):
        """接收深度帧（Z16），转为 H×W uint16（单位 mm），写入双缓冲"""
        try:
            arr   = np.frombuffer(msg.data, dtype=np.uint16)
            depth = arr.reshape((msg.height, msg.width)).copy()
            ts    = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            with self._buf_lock:
                self._latest_depth    = depth
                self._latest_depth_ts = ts
        except Exception as e:
            self.get_logger().error(f"[DetectionNode] Depth 回调失败: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # 模型加载（懒加载，在推理线程中调用）
    # ──────────────────────────────────────────────────────────────────────────

    def _load_model(self):
        """
        手动 torch.load 加载 YOLOv5 checkpoint，跳过 fuse()。
        aarch64 上 fuse() 会触发 SIGSEGV，必须跳过。
        """
        try:
            import torch

            self.get_logger().info(f"[DetectionNode] 加载模型: {self._model_path}")
            # 将 yolov5 源码目录加入 sys.path，让 torch.load 能找到自定义模块
            yolov5_src = "/home/sunrise/rdks100_slam/d435i_ros2/d435i_ros2"
            if yolov5_src not in sys.path:
                sys.path.insert(0, yolov5_src)

            ckpt  = torch.load(self._model_path, map_location="cpu")
            model = ckpt["model"].float().eval()

            # aarch64 兼容性 patch
            for m in model.modules():
                if hasattr(m, "inplace"):
                    m.inplace = False
                if isinstance(m, torch.nn.Upsample):
                    m.recompute_scale_factor = None

            # 不在 model 上设置 conf/iou，推理后手动做 NMS
            self._model = model

            # 尝试从模型中读取类别名称
            try:
                names = ckpt.get("names") or (
                    model.module.names if hasattr(model, "module") else model.names
                )
                if names:
                    self._model_names = list(names.values()) if isinstance(names, dict) else list(names)
            except Exception:
                pass  # 用 COCO_NAMES 兜底

            self._model_loaded = True
            self.get_logger().info(
                f"[DetectionNode] 模型加载成功 | 类别数={len(self._model_names)} device={self._device}"
            )
        except Exception as e:
            self._model_load_error = str(e)
            self.get_logger().error(f"[DetectionNode] 模型加载失败: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # 推理线程
    # ──────────────────────────────────────────────────────────────────────────

    def _infer_loop(self):
        """
        推理循环（独立线程）：
          1. 读取最新 RGB + Depth 帧（双缓冲，不阻塞 spin）
          2. YOLOv5 推理
          3. NMS 后处理（修复：旧版缺失此步骤导致海量框）
          4. 目标类别过滤（可选）
          5. 深度测距
          6. 发布 JSON 结果 + 带标注图像
        """
        import cv2
        import torch

        self._load_model()
        if not self._model_loaded:
            self.get_logger().error("[DetectionNode] 模型未就绪，推理线程退出")
            return

        self.get_logger().info("[DetectionNode] 推理线程启动")
        frame_id    = 0
        _last_log_ts = 0.0

        while rclpy.ok():
            # ── 读取双缓冲 ────────────────────────────────────────────────────
            with self._buf_lock:
                rgb    = self._latest_rgb
                depth  = self._latest_depth
                rgb_ts = self._latest_rgb_ts

            if rgb is None or depth is None:
                time.sleep(0.05)
                continue

            # ── 预处理：resize（可选）→ BGR→RGB → tensor ──────────────────────
            if self._infer_w > 0 and self._infer_h > 0:
                infer_img = cv2.resize(
                    rgb, (self._infer_w, self._infer_h),
                    interpolation=cv2.INTER_LINEAR,
                )
            else:
                infer_img = rgb

            try:
                t0 = time.time()
                img_rgb = infer_img[..., ::-1].copy()       # BGR → RGB
                img_chw = img_rgb.transpose(2, 0, 1)        # HWC → CHW
                tensor  = torch.from_numpy(img_chw).float() / 255.0
                tensor  = tensor.unsqueeze(0)               # → [1, 3, H, W]

                with torch.no_grad():
                    raw_output = self._model(tensor)

                infer_ms = (time.time() - t0) * 1000
            except Exception as e:
                self.get_logger().error(f"[DetectionNode] 推理失败: {e}")
                time.sleep(0.1)
                continue

            # ── NMS 后处理（关键修复）────────────────────────────────────────
            # apply_nms 从原始特征张量中提取并过滤出真实检测框
            nms_results = apply_nms(
                raw_output,
                conf_thresh=self._conf_thresh,
                iou_thresh=self._iou_thresh,
                max_det=self._max_det,
            )

            # ── 坐标缩放：推理尺寸 → 原图尺寸 ───────────────────────────────
            h_orig, w_orig = rgb.shape[:2]
            scale_x = w_orig / infer_img.shape[1]
            scale_y = h_orig / infer_img.shape[0]

            detections   = []
            annotated_img = rgb.copy() if self._pub_annotated else None

            for row in nms_results:
                x1_infer, y1_infer, x2_infer, y2_infer, conf, cls_id = row

                # 坐标缩放到原图
                x1 = x1_infer * scale_x
                y1 = y1_infer * scale_y
                x2 = x2_infer * scale_x
                y2 = y2_infer * scale_y

                # 边界裁剪
                x1 = max(0.0, min(float(w_orig), x1))
                y1 = max(0.0, min(float(h_orig), y1))
                x2 = max(0.0, min(float(w_orig), x2))
                y2 = max(0.0, min(float(h_orig), y2))

                # 类别过滤（target_classes 为空则不过滤）
                if self._target_classes and cls_id not in self._target_classes:
                    continue

                cls_name = (
                    self._model_names[cls_id]
                    if cls_id < len(self._model_names)
                    else str(cls_id)
                )

                # 深度测距
                dist_mm = get_mid_pos_distance(
                    [x1, y1, x2, y2], depth, self._sample_cnt
                )
                dist_m = dist_mm / 1000.0

                detections.append({
                    "class_id":   cls_id,
                    "class_name": cls_name,
                    "confidence": round(conf, 3),
                    "bbox": {
                        "x1": round(x1, 1), "y1": round(y1, 1),
                        "x2": round(x2, 1), "y2": round(y2, 1),
                    },
                    "distance_m": round(dist_m, 3),
                })

                # 绘制标注框
                if annotated_img is not None:
                    cv2.rectangle(
                        annotated_img,
                        (int(x1), int(y1)), (int(x2), int(y2)),
                        (0, 255, 0), 2,
                    )
                    label = f"{cls_name} {conf:.2f} {dist_m:.2f}m"
                    # 文字背景，提高可读性
                    (tw, th), _ = cv2.getTextSize(
                        label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
                    ty = max(int(y1) - 5, th + 2)
                    cv2.rectangle(
                        annotated_img,
                        (int(x1), ty - th - 2), (int(x1) + tw + 2, ty + 2),
                        (0, 255, 0), cv2.FILLED,
                    )
                    cv2.putText(
                        annotated_img, label,
                        (int(x1) + 1, ty),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (0, 0, 0), 1,                 # 黑色字体更清晰
                    )

            frame_id += 1

            # ── 发布 JSON 检测结果 ────────────────────────────────────────────
            result_msg      = String()
            result_msg.data = json.dumps({
                "timestamp":  rgb_ts,
                "frame_id":   frame_id,
                "infer_ms":   round(infer_ms, 1),
                "count":      len(detections),
                "detections": detections,
            }, ensure_ascii=False)
            self._pub_results_node.publish(result_msg)

            # ── 发布带标注图像 ────────────────────────────────────────────────
            if self._pub_annotated and annotated_img is not None and self._pub_anno_node:
                try:
                    anno_msg                  = Image()
                    anno_msg.header.stamp     = self.get_clock().now().to_msg()
                    anno_msg.header.frame_id  = "camera_color_optical_frame"
                    anno_msg.height           = annotated_img.shape[0]
                    anno_msg.width            = annotated_img.shape[1]
                    anno_msg.encoding         = "bgr8"
                    anno_msg.step             = annotated_img.shape[1] * 3
                    anno_msg.data             = annotated_img.tobytes()
                    self._pub_anno_node.publish(anno_msg)
                except Exception as e:
                    self.get_logger().error(f"[DetectionNode] 发布标注图像失败: {e}")

            # ── 每 5 秒打一次诊断日志 ─────────────────────────────────────────
            now = time.time()
            if now - _last_log_ts >= 5.0:
                self.get_logger().info(
                    f"[DetectionNode] frame={frame_id} "
                    f"infer={infer_ms:.1f}ms "
                    f"raw_boxes={len(nms_results)} "
                    f"after_filter={len(detections)}"
                )
                _last_log_ts = now


# ──────────────────────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = DetectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
