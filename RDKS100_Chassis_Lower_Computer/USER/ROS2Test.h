#ifndef _ROS2_TEST_H_
#define _ROS2_TEST_H_

#include "include.h"

// 测试速度控制转换
void Test_VelocityConversion(void);

// 测试舵机角度转换
void Test_ServoConversion(void);

// 测试里程计数据发送
void Test_OdomSend(void);

// 测试校验和计算
void Test_Checksum(void);

// 打印底盘参数
void Print_ChassisParams(void);

// 运行所有测试
void RunAllTests(void);

#endif // _ROS2_TEST_H_
