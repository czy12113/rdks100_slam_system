from setuptools import find_packages, setup
import os
from glob import glob

package_name = "d435i_detection"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages",
         [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        # launch 文件
        (os.path.join("share", package_name, "launch"),
         glob("launch/*.py")),
        # config 文件
        (os.path.join("share", package_name, "config"),
         glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="kkk",
    maintainer_email="kkk@todo.todo",
    description="D435i + YOLOv5 目标检测 + 深度测距 ROS2 节点",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            # ros2 run d435i_detection detection_node
            "detection_node = d435i_detection.detection_node:main",
            "detection_node_bpu = d435i_detection.detection_node_bpu:main",
            # 火/烟检测（CPU YOLOv5，独立于通用 BPU 检测）
            "fire_smoke_node = d435i_detection.fire_smoke_node:main",
        ],
    },
)
