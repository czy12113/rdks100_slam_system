#ifndef _CHASSIS_PARAMS_H_
#define _CHASSIS_PARAMS_H_

#include "include.h"

/*建议先用保守参数烧录测试，
重点从 MAX_LINEAR_SPEED、MAX_ANGULAR_SPEED、MOTOR_ACCEL_STEP、
MOTOR_DECEL_STEP、SERVO_LEFT_MAX/SERVO_RIGHT_MAX 开始调。*/

/* Chassis geometry, measured on the car. */
#define WHEELBASE           0.170f
#define TRACK_WIDTH         0.175f
#define WHEEL_DIAMETER      0.0604f
#define WHEEL_RADIUS        (WHEEL_DIAMETER / 2.0f)

/* Non-blocking task periods. TIM2 calls ROS2_TimerCallback() every 1 ms. */
#define CONTROL_TASK_PERIOD_MS      5
#define SERVO_TASK_PERIOD_MS        20
#define MOTOR_TASK_PERIOD_MS        40
#define ODOM_UPDATE_PERIOD_MS       100
#define ODOM_SEND_PERIOD_MS         100

/* Command safety. If no valid non-zero command arrives in this window, stop. */
#define CMD_TIMEOUT_MS              300

/* Keep protocol UART clean. Set to 1 only when USART1 is not used by RDK. */
#define DEBUG_PROTOCOL_UART         0

/* Steering and speed limits. Start conservatively, then tune on the car.
 * NOTE: keep MAX_LINEAR_SPEED / MAX_ANGULAR_SPEED in sync with stm32_bridge.py
 * (max_linear / max_angular). Mismatch causes saturation differences between
 * the upper computer and STM32, which then look like odom / steering bias.
 */
#define MAX_STEERING_ANGLE          0.87f
#define MIN_TURNING_RADIUS          0.200f
#define MAX_LINEAR_SPEED            0.60f
#define MAX_ANGULAR_SPEED           1.20f
#define LINEAR_DEADBAND             0.02f
#define ANGULAR_DEADBAND            0.005f

/* Motor driver parameters and output ramp. */
#define MOTOR_DIRECT_COMMAND_ENABLE 1
#define MOTOR_STOP_RETRY_COUNT      2

/* Encoder / odometry options.
 *   ODOMETRY_READ_ENCODER       : 1 = read encoders over the shared I2C bus
 *                                 (may block motor stop frames; see I2CMotor.c)
 *                                 0 = do not read encoders (open loop)
 *   ODOM_SEND_WITHOUT_ENCODER   : 1 = still send an odom frame even when
 *                                 encoders are disabled. Off by default so we
 *                                 never publish all-zero odom to the upper
 *                                 computer, which would corrupt Nav2 / AMCL
 *                                 and zero the velocity bars in the UI.
 *   ODOM_USE_ACKERMANN_MODEL    : 1 = compute yaw from the steering angle of
 *                                 the front servo (Ackermann, correct for
 *                                 this chassis). 0 = legacy differential
 *                                 formula (delta_yaw = (dr - dl) / TRACK).
 *                                 The differential formula yields delta_yaw=0
 *                                 whenever both rear wheels read the same
 *                                 count, which is the usual case here and is
 *                                 what was producing Nav2 yaw drift.
 *   ODOM_ENCODER_FAIL_LIMIT     : how many consecutive encoder read failures
 *                                 the odom layer tolerates before declaring
 *                                 the odom data invalid.
 */
/* v7.0 闭环 odom 方案现场验证未通过 (电机速度仍被锁死), 回滚到 v6.10:
 * 编码器关闭, 上位机 stm32_bridge 用 open_loop 模式给 Nav2/AMCL 提供 odom.
 * 留 ODOMETRY_READ_ENCODER 注释在这里以便后续重启该方案时一键切换.
 */
#define ODOMETRY_READ_ENCODER       0
#define ODOM_SEND_WITHOUT_ENCODER   0
#define ODOM_USE_ACKERMANN_MODEL    1
#define ODOM_ENCODER_FAIL_LIMIT     5
#define ENCODER_PPR                 11
#define GEAR_RATIO                  56.0f
#define MOTOR_MAX_RPM               200
#define MOTOR_ACCEL_STEP            4
#define MOTOR_DECEL_STEP            8
#define MOTOR_MIN_CHANGE            1

/* Steering servo pulse range. The safe range reduces jitter and end-stop load. */
#define SERVO_CENTER_ANGLE          1500
#define SERVO_LEFT_MAX              1150
#define SERVO_RIGHT_MAX             1850
#define SERVO_ANGLE_RANGE           180.0f
#define SERVO_CMD_DEADBAND_US       8
#define SERVO_TARGET_DEADBAND_US    3
#define SERVO_TURN_TIME_MS          180
#define SERVO_CENTER_TIME_MS        120
#define SERVO_INIT_TIME_MS          500

/* Math constants. */
#define PI                          3.14159265358979323846f
#define DEG_TO_RAD                  (PI / 180.0f)
#define RAD_TO_DEG                  (180.0f / PI)

#endif
