#ifndef _ROS2_PROTOCOL_H_
#define _ROS2_PROTOCOL_H_

#include "include.h"

#define FRAME_HEADER_0      0xAA
#define FRAME_HEADER_1      0x55
#define FRAME_TAIL          0x0D

#define ODOM_HEADER_0       0xBB
#define ODOM_HEADER_1       0x66

#define CMD_VELOCITY        0x01
#define CMD_STOP            0x02
#define CMD_RESET           0x03
#define CMD_GET_ODOM        0x04
#define CMD_SET_PARAM       0x05

#define DATA_TYPE_ODOM      0x01
#define DATA_TYPE_STATUS    0x02

#if defined(__CC_ARM)
#define ROS2_PACKED         __packed
#define ROS2_PACKED_POST
#else
#define ROS2_PACKED
#define ROS2_PACKED_POST    __attribute__((packed))
#endif

/* RDK -> STM32 control command, 10 bytes. */
typedef ROS2_PACKED struct {
    uint8  header[2];
    uint8  cmd_type;
    int16  linear_vel;
    int16  angular_vel;
    uint8  reserved;
    uint8  checksum;
    uint8  tail;
} ROS2_PACKED_POST ControlCmd_t;

/*
 * STM32 -> RDK odometry frame, 20 bytes:
 * BB 66, type, x(int32), y(int32), yaw(int16),
 * linear(int16), angular(int16), reserved, checksum, 0D.
 *
 * The current stm32_bridge.py reads exactly 20 bytes and checks
 * checksum = sum(frame[2:18]) & 0xFF, so there is one reserved byte
 * at frame[17].
 */
typedef ROS2_PACKED struct {
    uint8  header[2];
    uint8  data_type;
    int32  pos_x;
    int32  pos_y;
    int16  yaw;
    int16  linear_vel;
    int16  angular_vel;
    uint8  reserved;
    uint8  checksum;
    uint8  tail;
} ROS2_PACKED_POST OdomData_t;

/* STM32 -> RDK status frame, 12 bytes. */
typedef ROS2_PACKED struct {
    uint8  header[2];
    uint8  data_type;
    uint8  battery_level;
    int16  motor_current;
    uint16 error_code;
    uint8  status;
    uint8  checksum;
    uint8  tail;
} ROS2_PACKED_POST StatusData_t;

void ROS2Protocol_Init(void);
void ROS2Protocol_ProcessByte(uint8 data);
void ROS2Protocol_1msTick(void);
uint8 ROS2Protocol_TakeTimeoutStop(void);

void ROS2Protocol_SendOdom(int32 pos_x, int32 pos_y, int16 yaw,
                           int16 linear_vel, int16 angular_vel);

void ROS2Protocol_SendStatus(uint8 battery, int16 current,
                             uint16 error, uint8 status);

void ROS2Protocol_Task(void);
uint8 ROS2Protocol_CalcChecksum(uint8* data, uint8 len);

#endif
