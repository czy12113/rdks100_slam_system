#include "include.h"

// 全局变量
static int8_t MotorType = MOTOR_TYPE_JGB37_520_12V_110RPM;
static int8_t MotorEncoderPolarity = 0;

/* Software lock for the shared software-I2C bus.
 *
 * Background: motor writes (SetSpeed / Stop) and encoder reads share the
 * exact same software-I2C bus. A single encoder read transfers 16 bytes and
 * blocks several milliseconds; a stop frame must succeed within the control
 * window (5 ms task). Mixing them on a bare-metal Cortex-M is what causes
 * "motor locked at last speed" when ODOMETRY_READ_ENCODER=1, because a stop
 * frame can be queued while the encoder read still holds the bus.
 *
 * Strategy:
 *   - Motor writes (high priority) lock the bus for the duration of the
 *     write/retry sequence (a few hundred microseconds typical).
 *   - Encoder reads (low priority) check the flag, back off if busy
 *     (returning 2 so the odom layer treats this period as a miss), and do
 *     NOT retry or recover the bus on failure. Next 100 ms tick will retry.
 *
 * This is single-core, single-threaded code; the lock is purely advisory
 * between the foreground tasks and is safe without atomics because every
 * caller runs in the main while-loop, not from an interrupt.
 */
static volatile uint8_t I2CMotor_BusBusy = 0;

static void I2CMotor_BusLockBegin(void)
{
	I2CMotor_BusBusy = 1;
}

static void I2CMotor_BusLockEnd(void)
{
	I2CMotor_BusBusy = 0;
}

uint8_t I2CMotor_BusIsBusy(void)
{
	return I2CMotor_BusBusy;
}

static void I2CMotor_RecoverBus(void)
{
	uint8_t i;

	I2C_SDA_IN();
	IIC_SCL = 1;
	DelayUs(5);

	for(i = 0; i < 9; i++)
	{
		if(READ_SDA)
		{
			break;
		}
		IIC_SCL = 0;
		DelayUs(5);
		IIC_SCL = 1;
		DelayUs(5);
	}

	IIC_stop();
	DelayMs(1);
}

// I2C 读取函数
static uint8_t I2C_Read_Len(uint8_t Reg, uint8_t *Buf, uint8_t Len)
{
	uint8_t i;
	IIC_start();
	IIC_send_byte((CAM_DEFAULT_I2C_ADDRESS << 1) | 0);
	if(IIC_wait_ack() == 1)
	{
		IIC_stop();
		return 1;
	}
	IIC_send_byte(Reg);
	if(IIC_wait_ack() == 1)
	{
		IIC_stop();
		return 1;
	}
	IIC_start();
	IIC_send_byte((CAM_DEFAULT_I2C_ADDRESS << 1) | 1);
	if(IIC_wait_ack() == 1)
	{
		IIC_stop();
		return 1;
	}
	for(i=0; i<Len; i++)
	{
		if(i != Len-1)
			Buf[i] = IIC_read_byte(1);
		else
			Buf[i] = IIC_read_byte(0);
	}
	IIC_stop();
	return 0;
}

// I2C 写入函数
static int8_t I2C_Write_Len(int8_t Reg, int8_t *Buf, int8_t Len)
{
	uint8_t i;
	IIC_start();
	IIC_send_byte((CAM_DEFAULT_I2C_ADDRESS << 1) | 0);
	if(IIC_wait_ack() == 1)
	{
		IIC_stop();
		return 1;
	}
	IIC_send_byte(Reg);
	if(IIC_wait_ack() == 1)
	{
		IIC_stop();
		return 1;
	}
	for(i=0; i<Len; i++)
	{
		IIC_send_byte(Buf[i]);
		if(IIC_wait_ack() == 1)
		{
			IIC_stop();
			return 1;
		}
	}
	IIC_stop();
	return 0;
}

static uint8_t I2CMotor_WriteRetry(int8_t Reg, int8_t *Buf, int8_t Len, uint8_t repeats)
{
	uint8_t i;

	if(repeats == 0)
	{
		repeats = 1;
	}

	for(i = 0; i < repeats; i++)
	{
		if(I2C_Write_Len(Reg, Buf, Len) == 0)
		{
			return 0;
		}

		I2CMotor_RecoverBus();
		DelayMs(2);
	}

	return 1;
}

// 初始化 I2C 电机驱动器
void I2CMotor_Init(void)
{
	// 设置电机类型
	I2CMotor_WriteRetry(MOTOR_TYPE_ADDR, &MotorType, 1, 3);
	DelayMs(5);
	
	// 设置编码器极性
	I2CMotor_WriteRetry(MOTOR_ENCODER_POLARITY_ADDR, &MotorEncoderPolarity, 1, 3);
	DelayMs(5);
}

// 设置所有电机相同速度
// speed: -100 ~ 100 (负数后退，正数前进)
uint8_t I2CMotor_SetSpeed(int8 speed)
{
	int8_t motorSpeed[4];
	uint8_t result;

	motorSpeed[0] = speed;
	motorSpeed[1] = speed;
	motorSpeed[2] = speed;
	motorSpeed[3] = speed;

	I2CMotor_BusLockBegin();
	result = I2CMotor_WriteRetry(MOTOR_FIXED_SPEED_ADDR, motorSpeed, 4, 3);
	I2CMotor_BusLockEnd();
	return result;
}

// 单独设置每个电机速度
// m1: 左前, m2: 右前, m3: 左后, m4: 右后
uint8_t I2CMotor_SetSpeedIndividual(int8 m1, int8 m2, int8 m3, int8 m4)
{
	int8_t motorSpeed[4];
	uint8_t result;

	motorSpeed[0] = m1;
	motorSpeed[1] = m2;
	motorSpeed[2] = m3;
	motorSpeed[3] = m4;

	I2CMotor_BusLockBegin();
	result = I2CMotor_WriteRetry(MOTOR_FIXED_SPEED_ADDR, motorSpeed, 4, 3);
	I2CMotor_BusLockEnd();
	return result;
}

// 停止所有电机
uint8_t I2CMotor_Stop(void)
{
	return I2CMotor_StopReliable(MOTOR_STOP_RETRY_COUNT);
}

uint8_t I2CMotor_StopReliable(uint8_t repeats)
{
	int8_t stop[4] = {0, 0, 0, 0};
	uint8_t i;
	uint8_t success;

	if(repeats == 0)
	{
		repeats = 1;
	}

	I2CMotor_BusLockBegin();
	success = 1;
	for(i = 0; i < repeats; i++)
	{
		if(I2C_Write_Len(MOTOR_FIXED_SPEED_ADDR, stop, 4) == 0)
		{
			success = 0;
		}
		else
		{
			I2CMotor_RecoverBus();
		}
		DelayMs(2);
	}
	I2CMotor_BusLockEnd();

	return success;
}

// 读取电池电压
// voltage: 输出电压值 (mV)
// 返回: 0=成功, 1=失败
uint8_t I2CMotor_ReadVoltage(uint16 *voltage)
{
	uint8_t data[2];
	
	if(I2C_Read_Len(ADC_BAT_ADDR, data, 2) == 0)
	{
		*voltage = data[0] + (data[1] << 8);
		return 0;
	}
	return 1;
}

// 读取编码器值
// encoder: 输出4个编码器的值
// 返回: 0=成功, 1=失败, 2=总线被电机写占用，本周期跳过
//
// 读编码器是低优先级任务：不重试，不做总线恢复，不阻塞
// 电机写帧。当 I2CMotor_BusIsBusy() 为真时直接返回 2，让上层把
// 本周期视为读失败处理（保持 odom_valid=0），下个 100ms 周期再
// 尝试。这样无论是否启用 ODOMETRY_READ_ENCODER，电机停止帧都
// 不会被编码器读阻塞 —— 这是问题②的核心修复。
uint8_t I2CMotor_ReadEncoder(int32_t *encoder)
{
	uint8_t result;

	if(I2CMotor_BusBusy)
	{
		return 2;
	}

	I2CMotor_BusLockBegin();
	result = I2C_Read_Len(MOTOR_ENCODER_TOTAL_ADDR, (uint8_t*)encoder, 16);
	I2CMotor_BusLockEnd();
	return result;
}

// 复位编码器
void I2CMotor_ResetEncoder(void)
{
	int8_t reset[16] = {0};
	I2C_Write_Len(MOTOR_ENCODER_TOTAL_ADDR, reset, 16);
}
