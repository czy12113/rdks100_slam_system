from setuptools import find_packages, setup
import os
from glob import glob

package_name = "vlm_scene"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages",
         [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (os.path.join("share", package_name, "launch"),
         glob("launch/*.py")),
        (os.path.join("share", package_name, "config"),
         glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="kkk",
    maintainer_email="kkk@todo.todo",
    description="VLM 场景理解：检测框 → ROI → VLM 大模型 → 自然语言场景描述",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            # ros2 run vlm_scene vlm_node
            "vlm_node = vlm_scene.vlm_node:main",
        ],
    },
)
