#ifndef _I2C_MOTOR_H_
#define _I2C_MOTOR_H_

#include "include.h"

// I2C 电机驱动器地址定义
#define CAM_DEFAULT_I2C_ADDRESS       (0x34)
#define MOTOR_TYPE_ADDR               0x14
#define MOTOR_FIXED_SPEED_ADDR        0x33
#define MOTOR_ENCODER_POLARITY_ADDR   0x15
#define MOTOR_FIXED_PWM_ADDR          0x1F
#define MOTOR_ENCODER_TOTAL_ADDR      0x3C
#define ADC_BAT_ADDR                  0x00

// 电机类型定义
#define MOTOR_TYPE_WITHOUT_ENCODER        0
#define MOTOR_TYPE_TT                     1
#define MOTOR_TYPE_N20                    2
#define MOTOR_TYPE_JGB37_520_12V_110RPM   3

// 函数声明
void I2CMotor_Init(void);
uint8_t I2CMotor_SetSpeed(int8 speed);
uint8_t I2CMotor_SetSpeedIndividual(int8 m1, int8 m2, int8 m3, int8 m4);
uint8_t I2CMotor_Stop(void);
uint8_t I2CMotor_StopReliable(uint8_t repeats);
uint8_t I2CMotor_ReadVoltage(uint16 *voltage);
/* Returns 0 on success, 1 on transfer error, 2 if the I2C bus is currently
 * being used by a motor write/stop (caller should skip this period and try
 * again later instead of forcing a retry).
 */
uint8_t I2CMotor_ReadEncoder(int32_t *encoder);
void I2CMotor_ResetEncoder(void);

/* Software lock state of the shared software-I2C bus. */
uint8_t I2CMotor_BusIsBusy(void);

#endif
