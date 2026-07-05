# RDK S100 风扇温度曲线守护

板子型号：D-Robotics RDK S100 V1P0
风扇控制器：SMSC/EMC2305 (I2C 4-002f) — /sys/class/hwmon/hwmon1
温度源：/sys/class/thermal/thermal_zone{0,1,4}/temp（CPU/CPU/BPU，取 max）

## 文件
- `fan_curve.py` — 守护脚本（5s 轮询）
- `rdk-fan-curve.service` — systemd unit（root 跑）

## 装机命令（需要 sudo 权限）
```bash
sudo cp /home/sunrise/rdks100_slam/fan-curve/rdk-fan-curve.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rdk-fan-curve.service
```

## 验收
```bash
# 看守护日志
sudo journalctl -u rdk-fan-curve.service -f

# 看温度 / PWM / RPM
watch -n 1 'cat /sys/class/thermal/thermal_zone0/temp; \
            cat /sys/class/hwmon/hwmon1/pwm1; \
            cat /sys/class/hwmon/hwmon1/fan1_input'
```

## 调曲线
改 `fan_curve.py` 里的 `CURVE` 列表：(温度°C, PWM 0-255)
默认：
| 温度上限 | PWM | 含义 |
|----------|-----|------|
| 45°C     | 77  | 30% 低噪 |
| 55°C     | 128 | 50% 正常 |
| 65°C     | 191 | 75% 提速 |
| 75°C     | 230 | 90% 高效 |
| >75°C    | 255 | 100% 救命 |

## 临时停掉曲线还原默认
```bash
sudo systemctl stop rdk-fan-curve.service
# 手动把 pwm 设回 50%
echo 128 | sudo tee /sys/class/hwmon/hwmon1/pwm1
```

## 卸载
```bash
sudo systemctl disable --now rdk-fan-curve.service
sudo rm /etc/systemd/system/rdk-fan-curve.service
sudo systemctl daemon-reload
```

## 重要：发热的真正根因
即使装了曲线也压不住 detection_node 跑 YOLOv5s CPU 推理时的一核 97% 占用。
- 治本：换 BPU 模型（yolov5s.bin）或把 detection_node 改成定时跑
- 治标：加主动散热（铝壳开孔 / 加外置 5V 风扇吹顶面）/ 拉低 CPU 频率
