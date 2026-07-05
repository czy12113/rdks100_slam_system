# TJC串口屏按钮事件配置完整指南

## 硬件信息
- **型号**: TJC8048X571_011C
- **HMI软件版本**: v1.67.6
- **波特率**: 115200
- **连接**: RDK S100 ↔ USB转TTL ↔ TJC串口屏

---

## 问题症状
按TJC屏幕按钮，串口监听只收到 `00 00 00 FF FF FF`（启动响应），没有触摸事件数据。

---

## 根本原因
`printh` 命令**配置位置错误**或**未正确配置按钮事件**。

---

## 正确配置步骤（重要！）

### 步骤1：设置全局波特率
1. 在HMI软件主界面，点击 **"程序"** → **"程序属性"**
2. 找到 **"串口设置"** 或 **"Serial Settings"**
3. 设置波特率为 **115200**
4. 点击 **"确定"** 保存

### 步骤2：配置按钮触摸事件
以"前进按钮"（ID=12）为例：

1. **双击按钮组件**，打开属性面板
2. 在右侧找到 **"事件"** 标签页（或 "Event"）
3. 选择 **"弹起事件"** 标签（Touch Release Event）
   - 注意：也可以用"按下事件"（Touch Press Event），但弹起事件更常用
4. 在代码框中输入：
   ```
   printh 65 00 0C 01 FF FF FF
   ```
   
   **重要说明：**
   - `printh` 后面用**空格**分隔十六进制数
   - **不要**加 `0x` 前缀
   - 数据格式：`65 [页面ID] [组件ID] [事件类型] FF FF FF`
     - `65`: 触摸事件标识
     - `00`: 页面ID（主页面=0）
     - `0C`: 组件ID（12的十六进制）
     - `01`: 事件类型（0x01=按下，0x00=释放）
     - `FF FF FF`: 帧尾

5. 点击 **"确定"** 保存

### 步骤3：配置所有按钮
按照相同方法配置其他按钮：

| 按钮功能 | 组件ID | 十六进制 | printh命令 |
|---------|--------|---------|-----------|
| 前进 | 12 | 0C | `printh 65 00 0C 01 FF FF FF` |
| 后退 | 13 | 0D | `printh 65 00 0D 01 FF FF FF` |
| 急停 | 14 | 0E | `printh 65 00 0E 01 FF FF FF` |
| 左转 | 15 | 0F | `printh 65 00 0F 01 FF FF FF` |
| 停止 | 16 | 10 | `printh 65 00 10 01 FF FF FF` |
| 右转 | 17 | 11 | `printh 65 00 11 01 FF FF FF` |

### 步骤4：编译和烧录
1. 点击 **"编译"** 按钮（或按 F5）
2. 确认编译成功（无错误）
3. 点击 **"上传"** 按钮，烧录到串口屏
4. 等待烧录完成

### 步骤5：重启串口屏
**重要：** 必须重新上电串口屏，配置才会生效！
- 拔掉电源，等待3秒
- 重新插上电源

---

## 验证配置是否成功

### 方法1：在RDK S100上监听原始数据
```bash
# 停止ROS节点（避免占用串口）
ros2 node kill /tjc_hmi_bridge

# 配置串口
stty -F /dev/ttyUSB1 115200 raw

# 监听数据（十六进制显示）
cat /dev/ttyUSB1 | xxd
```

**按前进按钮，应该看到：**
```
00000000: 6500 0c01 ffff ff                        e......
```

**如果只看到：**
```
00000000: 0000 00ff ffff                           ......
```
说明按钮事件未配置或配置错误。

### 方法2：使用诊断脚本
```bash
cd ~/ros2_ws/src/czybot_navigation2/scripts
bash diagnose_tjc.sh
```

---

## 常见错误和解决方法

### 错误1：编译失败 "print 65 00 0c 01 ff ff ff"
**原因：** 使用了 `print` 而不是 `printh`  
**解决：** 改为 `printh 65 00 0C 01 FF FF FF`

### 错误2：编译成功但无数据发送
**原因：** 命令放在了错误的位置（如"初始化事件"）  
**解决：** 必须放在"弹起事件"或"按下事件"标签页

### 错误3：收到乱码数据
**原因：** 波特率不匹配  
**解决：** 
1. HMI软件中设置为115200
2. RDK S100上检查：`stty -F /dev/ttyUSB1 115200`

### 错误4：按钮按下无反应
**原因：** 未重启串口屏  
**解决：** 重新上电串口屏

---

## 替代方案：使用"发送组件ID"功能

如果 `printh` 方法仍有问题，可以尝试TJC的内置功能：

1. 双击按钮组件
2. 在属性面板找到 **"发送组件ID"** 选项
3. 勾选 **"弹起时发送"**
4. 编译烧录

**注意：** 这种方法发送的数据格式不同，需要修改ROS代码中的解析逻辑。

---

## ROS代码对应的解析逻辑

在 [`tjc_hmi_bridge.py`](../scripts/tjc_hmi_bridge.py:293) 中：

```python
def parse_hmi_command(self, data):
    """解析串口屏发来的指令"""
    # TJC触摸事件格式: 0x65 page_id component_id event_type
    if len(data) >= 4 and data[0] == 0x65:
        page_id = data[1]
        component_id = data[2]
        event_type = data[3]  # 0x01=按下, 0x00=释放
        
        if event_type == 0x01:  # 按下事件
            self.handle_button_press(page_id, component_id)
```

**数据流：**
```
TJC按钮 → printh 65 00 0C 01 FF FF FF 
         → 串口 /dev/ttyUSB1 
         → tjc_hmi_bridge.py 解析 
         → 发布 /cmd_vel 
         → stm32_bridge.py 订阅 
         → 串口 /dev/ttyUSB0 
         → STM32 
         → 电机
```

---

## 下一步排查

如果TJC配置正确但小车仍不动，问题在STM32通信链路：

```bash
# 运行STM32诊断脚本
cd ~/ros2_ws/src/czybot_navigation2/scripts
bash diagnose_stm32.sh
```

---

## 参考资料
- TJC串口屏指令集：查看HMI软件帮助文档
- 串口协议格式：见 [`tjc_hmi_bridge.py`](../scripts/tjc_hmi_bridge.py:1) 文件头注释
