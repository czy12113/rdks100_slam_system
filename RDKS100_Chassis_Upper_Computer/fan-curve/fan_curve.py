#!/usr/bin/env python3
"""
RDK S100 EMC2305 风扇温度曲线守护进程
- 读 /sys/class/thermal/thermal_zone0/temp (CPU t1, 单位 m°C)
- 按温度档位输出 PWM 到 /sys/class/hwmon/hwmon1/pwm1 (0-255)
- 曲线：温和调速，高温拉满，温和区不空转
"""
import os, sys, time, signal

PWM_PATH   = "/sys/class/hwmon/hwmon1/pwm1"
TEMP_PATHS = [
    "/sys/class/thermal/thermal_zone0/temp",  # CPU t1
    "/sys/class/thermal/thermal_zone1/temp",  # CPU t2
    "/sys/class/thermal/thermal_zone4/temp",  # BPU
]
INTERVAL = 5   # 秒

# (上限温度 °C, 目标 PWM 0-255)
# 温度从低到高匹配，第一个温度 ≥ 阈值的段生效
CURVE = [
    (45,  77),   # ≤45°C  → 30% (低噪)
    (55, 128),   # ≤55°C  → 50%
    (65, 191),   # ≤65°C  → 75%
    (75, 230),   # ≤75°C  → 90%
    (999, 255),  # >75°C  → 100% (拉满救命)
]

def read_max_temp():
    vals = []
    for p in TEMP_PATHS:
        try:
            v = int(open(p).read().strip())
            vals.append(v // 1000)   # m°C → °C
        except Exception:
            pass
    return max(vals) if vals else None

def set_pwm(pwm):
    pwm = max(0, min(255, int(pwm)))
    try:
        with open(PWM_PATH, "w") as f:
            f.write(str(pwm))
        return pwm
    except PermissionError:
        print(f"[FATAL] 没有写 {PWM_PATH} 的权限，需要 root 跑本程序", flush=True)
        sys.exit(2)
    except Exception as e:
        print(f"[ERR] 写 PWM 失败: {e}", flush=True)
        return None

def curve_pwm(temp_c):
    for thr, pwm in CURVE:
        if temp_c <= thr:
            return pwm
    return 255

running = True
def stop(*_):
    global running
    running = False
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

print(f"[fan-curve] 启动 | 采样间隔 {INTERVAL}s", flush=True)
print(f"[fan-curve] 监控: {TEMP_PATHS}", flush=True)
print(f"[fan-curve] PWM 输出: {PWM_PATH}", flush=True)

while running:
    t = read_max_temp()
    if t is not None:
        target = curve_pwm(t)
        actual = set_pwm(target)
        rpm_path = "/sys/class/hwmon/hwmon1/fan1_input"
        rpm = open(rpm_path).read().strip() if os.path.exists(rpm_path) else "?"
        print(f"[fan-curve] t={t:>2}°C pwm={actual:>3} rpm={rpm}", flush=True)
    time.sleep(INTERVAL)

# 退出时回到中速，不要全停
print("[fan-curve] 退出，恢复 128/255 50%", flush=True)
set_pwm(128)
