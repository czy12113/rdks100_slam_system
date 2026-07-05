#ifndef _SERIAL_CONTROL_H_
#define _SERIAL_CONTROL_H_

// 串口控制模块初始化
void SerialControlInit(void);

// 串口命令处理（在串口中断中调用）
void SerialControlProcess(uint8 data);

// 获取当前控制模式
uint8 SerialControlGetMode(void);

#endif
