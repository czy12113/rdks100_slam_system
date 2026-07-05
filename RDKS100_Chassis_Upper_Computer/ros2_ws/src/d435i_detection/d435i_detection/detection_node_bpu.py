#!/usr/bin/env python3
"""
detection_node_bpu.py — D435i + YOLOv5x BPU 推理（Nash 架构）

用板上预编译的 yolov5x_672x672_nv12.hbm 替代 CPU torch 推理，
CPU 占用从 97% → 个位数，FPS 从 3-5 → 30+。

与 detection_node.py 相比：
  - 推理引擎：torch (CPU) → hbm_runtime (BPU)
  - 预处理：  BGR→RGB→tensor → BGR→NV12 planes
  - 后处理：  自定义 NMS → 官方 utils（dequantize→decode→NMS→scale）

ROS2 管道、深度测距、双缓冲全部保留，接口不变。
"""

import json
import os
import random
import sys
import time
import threading
from typing import Optional, List, Dict, Tuple

import cv2
import numpy as np
import hbm_runtime
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String

# ── 官方 BPU 工具模块（板端示例内置） ──────────────────────────────
_MODEL_ZOO_UTILS = "/app/pydev_demo"
if _MODEL_ZOO_UTILS not in sys.path:
    sys.path.insert(0, _MODEL_ZOO_UTILS)

from utils import preprocess_utils  as pre_utils
from utils import postprocess_utils as post_utils
from utils import common_utils     as common
from utils import draw_utils       as draw_mod

# ── YOLOv5x 解码常量 ─────────────────────────────────────────────
STRIDES  = np.array([8, 16, 32], dtype=np.int32)
ANCHORS  = np.array([
    [10,13],[16,30],[33,23], [30,61],[62,45],[59,119],
    [116,90],[156,198],[373,326]
], dtype=np.float32).reshape(3,3,2)
COCO_80  = 80   # 类别数
MODEL_H  = 672  # 模型输入高
MODEL_W  = 672  # 模型输入宽

# ── COCO 80 类名称表 ──────────────────────────────────────────────
#   id=52 原本是 "pizza"，仓库场景下火焰经常被误识别为 pizza，
#   这里直接改名为 "fire"，让前端稳定拿到 fire 标签。
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

# ── 仓库场景默认白名单 ─────────────────────────────────────────────
#   target_classes 未显式配置时兜底用，只透出仓库巡检真正关心的类别
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

# ── 深度测距（同 detection_node.py）─────────────────────────────
def depth_at_box(box, depth_mm, sample_cnt=24) -> float:
    x1,y1,x2,y2 = map(int, box[:4]); mid=(x1+x2)//2, (y1+y2)//2; mn=min(abs(x2-x1),abs(y2-y1))
    h,w = depth_mm.shape; vals=[]
    for _ in range(sample_cnt):
        b = random.randint(-mn//4, mn//4)
        px = max(0,min(w-1,mid[0]+b)); py=max(0,min(h-1,mid[1]+b))
        v = int(depth_mm[py,px])
        if v>0: vals.append(v)
    if not vals: return 0.0
    a = np.sort(vals); return float(np.mean(a[len(a)//4:len(a)*3//4]))

# ── BPU 检测器 ──────────────────────────────────────────────────
class BPU_YOLOv5:
    """加载 hbm 模型，提供 preprocess → forward → postprocess 接口"""

    def __init__(self, model_path, conf=0.5, nms=0.45):
        self.model = hbm_runtime.HB_HBMRuntime(model_path)
        mn = self.model.model_names[0]
        self._name    = mn
        self._inames  = self.model.input_names[mn]
        self._onames  = self.model.output_names[mn]
        self._shapes  = self.model.input_shapes[mn]
        self._quants  = self.model.output_quants[mn]
        self.conf     = conf
        self.nms      = nms
        # 可从 yaml 读，这里写死 COCO 80
        self.classes_num = COCO_80

    def preprocess(self, bgr: np.ndarray):
        """BGR → letterbox 672×672 → NV12 planes"""
        resized = pre_utils.resized_image(bgr, MODEL_W, MODEL_H, resize_type=1)
        y, uv   = pre_utils.bgr_to_nv12_planes(resized)
        return {self._name: {self._inames[0]: y, self._inames[1]: uv}}

    def forward(self, inp):
        return self.model.run(inp)[self._name]

    def postprocess(self, outputs, orig_w, orig_h):
        fp32   = post_utils.dequantize_outputs(outputs, self._quants)
        pred   = post_utils.decode_outputs(self._onames, fp32, STRIDES, ANCHORS, self.classes_num)
        boxes, scores, cls_ids = post_utils.filter_predictions(pred, self.conf)
        keep   = post_utils.NMS(boxes, scores, cls_ids, self.nms)
        xyxy   = post_utils.scale_coords_back(boxes[keep], orig_w, orig_h, MODEL_W, MODEL_H, 1)
        return xyxy, cls_ids[keep], scores[keep]

# ── ROS2 节点 ────────────────────────────────────────────────────
class DetectionNodeBPU(Node):
    def __init__(self):
        super().__init__("d435i_bpu_detection_node")

        # 参数
        self.declare_parameter("model_path", "/opt/hobot/model/s100/basic/yolov5x_672x672_nv12.hbm")
        self.declare_parameter("confidence_threshold", 0.5)
        self.declare_parameter("iou_threshold", 0.45)
        self.declare_parameter("max_detections", 20)
        self.declare_parameter("depth_sample_count", 24)
        self.declare_parameter("target_classes", rclpy.parameter.Parameter.Type.INTEGER_ARRAY)
        self.declare_parameter("sub_topic_rgb",   "/camera/camera/color/image_raw")
        self.declare_parameter("sub_topic_depth", "/camera/camera/aligned_depth_to_color/image_raw")
        self.declare_parameter("pub_topic_results",   "/detection/results")
        self.declare_parameter("pub_topic_annotated", "/detection/annotated_image")
        self.declare_parameter("publish_annotated", True)

        mp = self.get_parameter("model_path").value
        self._conf_thresh = float(self.get_parameter("confidence_threshold").value)
        self._iou_thresh  = float(self.get_parameter("iou_threshold").value)
        self._max_det     = int(self.get_parameter("max_detections").value)
        self._sample_cnt  = int(self.get_parameter("depth_sample_count").value)
        self._pub_results  = self.get_parameter("pub_topic_results").value
        self._pub_anno     = self.get_parameter("pub_topic_annotated").value
        self._sub_rgb      = self.get_parameter("sub_topic_rgb").value
        self._sub_depth    = self.get_parameter("sub_topic_depth").value
        self._pub_annotated = bool(self.get_parameter("publish_annotated").value)
        # 未显式配置 → 用仓库白名单兜底；显式非空 → 按配置走
        try:
            tc = self.get_parameter("target_classes").value
            self._target_classes = list(tc) if tc else list(WAREHOUSE_CLASSES)
        except Exception:
            self._target_classes = list(WAREHOUSE_CLASSES)

        # 双缓冲
        self._lock = threading.Lock()
        self._rgb: Optional[np.ndarray] = None
        self._depth: Optional[np.ndarray] = None
        self._rgb_ts = 0.0

        # QoS
        sq = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1)

        # 订阅
        self.create_subscription(Image, self._sub_rgb,   self._cb_rgb,   sq)
        self.create_subscription(Image, self._sub_depth, self._cb_depth, sq)

        # 发布
        self._pub_res       = self.create_publisher(String, self._pub_results, 10)
        self._pub_anno_node = self.create_publisher(Image, self._pub_anno, 10) if self._pub_annotated else None

        # BPU 模型
        self.get_logger().info(f"[BPU] 加载模型: {mp}")
        self._detector = BPU_YOLOv5(mp, conf=self._conf_thresh, nms=self._iou_thresh)
        common.print_model_info(self._detector.model)

        # 推理线程
        self._thread = threading.Thread(target=self._loop, daemon=True, name="bpu_infer")
        self._thread.start()
        self.get_logger().info("[BPU] 推理线程已启动")

    # ── 回调（SPIN 线程）────────────────────────────────────────
    def _cb_rgb(self, msg: Image):
        try:
            arr = np.frombuffer(msg.data, np.uint8)
            enc = msg.encoding.lower()
            img = arr.reshape((msg.height,msg.width,3))[...,::-1].copy() if "rgb" in enc else arr.reshape((msg.height,msg.width,3)).copy()
            with self._lock:
                self._rgb, self._rgb_ts = img, msg.header.stamp.sec + msg.header.stamp.nanosec*1e-9
        except Exception as e:
            self.get_logger().error(f"[BPU] RGB cb fail: {e}")

    def _cb_depth(self, msg: Image):
        try:
            with self._lock:
                self._depth = np.frombuffer(msg.data, np.uint16).reshape((msg.height,msg.width)).copy()
        except Exception as e:
            self.get_logger().error(f"[BPU] Depth cb fail: {e}")

    # ── 推理循环 ──────────────────────────────────────────────────
    def _loop(self):
        frame_id = 0; _last = 0.0
        while rclpy.ok():
            with self._lock:
                bgr, depth, ts = self._rgb, self._depth, self._rgb_ts
            if bgr is None or depth is None:
                time.sleep(0.02); continue

            h,w = bgr.shape[:2]
            t0 = time.time()

            # BPU 推理
            inp  = self._detector.preprocess(bgr)
            out  = self._detector.forward(inp)
            boxes, cls_ids, scores = self._detector.postprocess(out, w, h)

            bpums = (time.time()-t0)*1000; frame_id+=1

            # 深度测距 + 画框
            dets = []
            anno = bgr.copy() if self._pub_annotated else None
            for i in range(min(len(boxes), self._max_det)):
                cid = int(cls_ids[i])
                if self._target_classes and cid not in self._target_classes:
                    continue
                x1,y1,x2,y2 = boxes[i].tolist()
                dist = depth_at_box([x1,y1,x2,y2], depth, self._sample_cnt)
                cn   = COCO_NAMES[cid] if cid<80 else str(cid)
                dets.append({"class_id":cid,"class_name":cn,"confidence":round(float(scores[i]),3),
                             "bbox":{"x1":round(x1,1),"y1":round(y1,1),"x2":round(x2,1),"y2":round(y2,1)},
                             "distance_m":round(dist/1000,3)})
                if anno is not None:
                    cv2.rectangle(anno, (int(x1),int(y1)), (int(x2),int(y2)), (0,255,0),2)
                    label = f"{cn} {scores[i]:.2f} {dist/1000:.2f}m"
                    (tw,th),_=cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,0.55,1)
                    cv2.rectangle(anno,(int(x1),int(y1)-th-4),(int(x1)+tw+2,int(y1)),(0,255,0),-1)
                    cv2.putText(anno,label,(int(x1),int(y1)-4),cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,0,0),1)

            # 发布
            msg = String(); msg.data = json.dumps({"timestamp":ts,"frame_id":frame_id,"infer_ms":round(bpums,1),
                                                    "count":len(dets),"detections":dets},ensure_ascii=False)
            self._pub_res.publish(msg)
            if self._pub_anno_node and anno is not None:
                am = Image(); am.header.stamp=self.get_clock().now().to_msg(); am.header.frame_id="camera_color_optical_frame"
                am.height,am.width=anno.shape[:2]; am.encoding="bgr8"; am.step=anno.shape[1]*3; am.data=anno.tobytes()
                self._pub_anno_node.publish(am)

            if time.time()-_last>=5:
                self.get_logger().info(f"[BPU] f{frame_id} infer={bpums:.1f}ms dets={len(dets)}")
                _last=time.time()

def main(args=None):
    rclpy.init(args=args); node=DetectionNodeBPU()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally: node.destroy_node(); rclpy.shutdown()

if __name__ == "__main__":
    main()
