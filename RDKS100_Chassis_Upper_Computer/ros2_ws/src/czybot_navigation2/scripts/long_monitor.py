#!/usr/bin/env python3
"""
长时间监听 STM32 数据
"""
import serial
import struct
import time


def main():
    port = '/dev/ttyUSB0'
    baudrate = 115200
    
    print("========================================")
    print("长时间监听 STM32 数据")
    print("========================================")
    print(f"串口: {port} @ {baudrate}")
    print("按 Ctrl+C 停止\n")
    
    try:
        ser = serial.Serial(port, baudrate, timeout=0.1)
        print("串口已打开")
        print("开始监听...\n")
        
        rx_buffer = bytearray()
        frame_count = 0
        last_time = time.time()
        
        while True:
            # 读取数据
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                rx_buffer.extend(data)
                
                # 显示原始数据
                current_time = time.time()
                if current_time - last_time >= 1.0:
                    print(f"[{int(current_time)}] 缓冲区: {len(rx_buffer)} 字节")
                    if len(rx_buffer) > 0:
                        print(f"  数据: {rx_buffer[:min(50, len(rx_buffer))].hex(' ')}")
                    last_time = current_time
                
                # 尝试解析 ROS2 帧
                while len(rx_buffer) >= 20:
                    # 查找帧头
                    if rx_buffer[0] == 0xBB and rx_buffer[1] == 0x66:
                        if len(rx_buffer) >= 20:
                            frame = bytes(rx_buffer[:20])
                            
                            # 验证帧尾
                            if frame[19] == 0x0D:
                                frame_count += 1
                                print(f"\n[帧 {frame_count}] ROS2 里程计帧:")
                                print(f"  原始: {frame.hex(' ')}")
                                
                                # 验证校验和
                                checksum_calc = sum(frame[2:18]) & 0xFF
                                checksum_recv = frame[18]
                                
                                if checksum_calc == checksum_recv:
                                    # 解析数据
                                    try:
                                        pos_x = struct.unpack('<i', frame[3:7])[0] / 1000.0
                                        pos_y = struct.unpack('<i', frame[7:11])[0] / 1000.0
                                        yaw = struct.unpack('<h', frame[11:13])[0] / 1000.0
                                        vx = struct.unpack('<h', frame[13:15])[0] / 1000.0
                                        vth = struct.unpack('<h', frame[15:17])[0] / 1000.0
                                        
                                        print(f"  ✓ 里程计: x={pos_x:.3f}m, y={pos_y:.3f}m, "
                                              f"yaw={yaw:.3f}rad, vx={vx:.3f}m/s, vth={vth:.3f}rad/s")
                                    except Exception as e:
                                        print(f"  ✗ 解析错误: {e}")
                                else:
                                    print(f"  ✗ 校验和错误: 计算={checksum_calc}, 接收={checksum_recv}")
                            
                            rx_buffer = rx_buffer[20:]
                        else:
                            break
                    else:
                        # 显示丢弃的字节
                        discarded = rx_buffer.pop(0)
                        if discarded >= 0x20 and discarded <= 0x7E:
                            print(f"丢弃: 0x{discarded:02x} ('{chr(discarded)}')")
                        else:
                            print(f"丢弃: 0x{discarded:02x}")
            
            time.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
        print("串口已关闭")


if __name__ == '__main__':
    main()
