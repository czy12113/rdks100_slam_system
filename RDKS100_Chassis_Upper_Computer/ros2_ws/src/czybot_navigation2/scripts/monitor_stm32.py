#!/usr/bin/env python3
"""
持续监听 STM32 数据，并尝试发送命令触发响应
"""
import serial
import struct
import time
import sys


def send_ros2_cmd(ser, linear_vel=0, angular_vel=0):
    """发送 ROS2 协议命令"""
    data = bytearray([0xAA, 0x55, 0x01])
    data.extend(struct.pack('<h', linear_vel))
    data.extend(struct.pack('<h', angular_vel))
    data.append(0x00)
    checksum = sum(data[2:7]) & 0xFF
    data.append(checksum)
    data.append(0x0D)
    ser.write(bytes(data))
    return data


def send_simple_cmd(ser, cmd):
    """发送简单串口命令"""
    ser.write(cmd.encode() + b'\r\n')


def main():
    port = '/dev/ttyUSB0'
    
    print("========================================")
    print("STM32 持续监听测试")
    print("========================================")
    print("按 Ctrl+C 停止\n")
    
    # 尝试 115200 (ROS2 协议)
    print("=== 测试 115200 波特率 (ROS2 协议) ===")
    try:
        ser = serial.Serial(port, 115200, timeout=0.1)
        print("串口已打开\n")
        
        rx_buffer = bytearray()
        last_send_time = time.time()
        send_count = 0
        
        print("开始监听（30秒）...")
        start_time = time.time()
        
        while time.time() - start_time < 30:
            # 每 2 秒发送一次命令
            if time.time() - last_send_time >= 2.0:
                send_count += 1
                cmd = send_ros2_cmd(ser, 0, 0)
                print(f"[{send_count}] 发送停止命令: {cmd.hex(' ')}")
                last_send_time = time.time()
            
            # 读取数据
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                rx_buffer.extend(data)
                
                print(f"收到 {len(data)} 字节: {data.hex(' ')}")
                
                # 尝试解析 ROS2 帧
                while len(rx_buffer) >= 20:
                    if rx_buffer[0] == 0xBB and rx_buffer[1] == 0x66:
                        frame = bytes(rx_buffer[:20])
                        print(f"  → ROS2 里程计帧: {frame.hex(' ')}")
                        
                        # 解析数据
                        try:
                            pos_x = struct.unpack('<i', frame[3:7])[0] / 1000.0
                            pos_y = struct.unpack('<i', frame[7:11])[0] / 1000.0
                            yaw = struct.unpack('<h', frame[11:13])[0] / 1000.0
                            vx = struct.unpack('<h', frame[13:15])[0] / 1000.0
                            vth = struct.unpack('<h', frame[15:17])[0] / 1000.0
                            print(f"  → 里程计: x={pos_x:.3f}m, y={pos_y:.3f}m, "
                                  f"yaw={yaw:.3f}rad, vx={vx:.3f}m/s, vth={vth:.3f}rad/s")
                        except:
                            pass
                        
                        rx_buffer = rx_buffer[20:]
                    else:
                        rx_buffer.pop(0)
            
            time.sleep(0.05)
        
        ser.close()
        print("\n115200 测试完成")
        
    except KeyboardInterrupt:
        print("\n用户中断")
        ser.close()
        return
    except Exception as e:
        print(f"错误: {e}")
    
    print("\n" + "="*40)
    
    # 尝试 9600 (简单串口控制)
    print("\n=== 测试 9600 波特率 (简单串口控制) ===")
    try:
        ser = serial.Serial(port, 9600, timeout=0.1)
        print("串口已打开\n")
        
        commands = ['X', 'W', 'S', 'A', 'D']
        
        print("开始监听（15秒）...")
        start_time = time.time()
        last_send_time = time.time()
        cmd_idx = 0
        
        while time.time() - start_time < 15:
            # 每 3 秒发送一次命令
            if time.time() - last_send_time >= 3.0:
                cmd = commands[cmd_idx % len(commands)]
                send_simple_cmd(ser, cmd)
                print(f"发送命令: {cmd}")
                cmd_idx += 1
                last_send_time = time.time()
            
            # 读取数据
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"收到: {data}")
                try:
                    text = data.decode('ascii', errors='ignore')
                    if text.strip():
                        print(f"  → 文本: {text}")
                except:
                    pass
            
            time.sleep(0.05)
        
        ser.close()
        print("\n9600 测试完成")
        
    except KeyboardInterrupt:
        print("\n用户中断")
        ser.close()
        return
    except Exception as e:
        print(f"错误: {e}")
    
    print("\n========================================")
    print("测试完成")
    print("========================================")


if __name__ == '__main__':
    main()
