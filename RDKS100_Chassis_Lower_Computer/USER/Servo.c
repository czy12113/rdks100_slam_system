#include "include.h"

uint16 ServoPwmDuty[8] = {1500,1500,1500,500,500,900,1500,1500}; 	 // PWM脉冲宽度 
uint16 ServoPwmDutySet[8] = {1500,1500,1500,500,500,900,1500,1500}; 	 // PWM脉冲宽度 
float  ServoPwmDutyInc[8]; 	 	 // 为了速度控制，当PWM脉宽发生变化时，每2.5ms或20ms递增的PWM脉宽 

bool ServoPwmDutyHaveChange = TRUE; 	 // 脉宽有变化标志位 

uint16 ServoTime = 2000; 	 	 	 // 舵机从当前角度运动到指定角度的时间，也就是控制速度 

static uint16 ServoAbsDiff(uint16 a, uint16 b)
{
	if(a > b)
	{
		return a - b;
	}

	return b - a;
}

void ServoSetPluseAndTime(uint8 id,uint16 p,uint16 time) 
{ 
	if((id > 0 || id ==0) && id <= 7 && p >= 500 && p <= 2500) 
	{ 
		if(ServoAbsDiff(ServoPwmDutySet[id], p) <= SERVO_TARGET_DEADBAND_US)
		{
			return;
		}

		if(time < 20) 
			time = 20; 
		if(time > 30000) 
			time = 30000; 

		ServoPwmDutySet[id] = p; 
		ServoTime = time; 
		ServoPwmDutyHaveChange = TRUE; 
	} 
}

// 立即设置舵机角度，无渐变延迟
void ServoSetPluseImmediate(uint8 id, uint16 p)
{
	if((id > 0 || id ==0) && id <= 7 && p >= 500 && p <= 2500) 
	{
		ServoPwmDuty[id] = p;
		ServoPwmDutySet[id] = p;
		ServoPwmDutyHaveChange = FALSE;  // 取消渐变标志
	}
} 

void ServoPwmDutyCompare(void)// 脉宽变化比较及速度控制 
{ 
	uint8 i; 
	static uint16 ServoPwmDutyIncTimes; 	 // 需要递增的次数 
	static bool ServoRunning = FALSE; 	 // 舵机正在以指定速度运动到指定的脉宽对应的位置 
	
	if(ServoPwmDutyHaveChange) 
	{ 
		ServoPwmDutyHaveChange = FALSE; 
		ServoPwmDutyIncTimes = ServoTime/20; 	 // 当每20ms调用一次ServoPwmDutyCompare()函数时用此句 
		if(ServoPwmDutyIncTimes == 0)
		{
			ServoPwmDutyIncTimes = 1;
		}
		for(i=0;i<8;i++) 
		{ 
			if(ServoPwmDutySet[i] > ServoPwmDuty[i]) 
			{ 
				ServoPwmDutyInc[i] = ServoPwmDutySet[i] - ServoPwmDuty[i]; 
			} 
			else 
			{ 
				ServoPwmDutyInc[i] = -(ServoPwmDuty[i] - ServoPwmDutySet[i]); 
			} 
			ServoPwmDutyInc[i] /= ServoPwmDutyIncTimes;// 每次递增的脉宽 
		} 
		ServoRunning = TRUE; 	 // 舵机开始动作 
	} 
	
	if(ServoRunning) 
	{ 
		ServoPwmDutyIncTimes--; 
		
		// 检查是否到达目标位置（在循环外判断）
		if(ServoPwmDutyIncTimes == 0) 
		{ 
			// 最后一次递增就直接将设定值赋给当前值 
			for(i=0;i<8;i++) 
			{ 
				ServoPwmDuty[i] = ServoPwmDutySet[i]; 
			}
			ServoRunning = FALSE; 	 // 到达设定位置，舵机停止运动 
		} 
		else 
		{ 
			// 渐变过程中
			for(i=0;i<8;i++) 
			{ 
				ServoPwmDuty[i] = ServoPwmDutySet[i] + 
					(signed short int)(ServoPwmDutyInc[i] * ServoPwmDutyIncTimes); 
			} 
		} 
	} 
} 

void InitTimer3(void) 
{ 
	NVIC_InitTypeDef NVIC_InitStructure; 
	RCC->APB1ENR|=1<<1;// TIM3时钟使能 
	TIM3->PSC=72 - 1;  // 预分频器72,得到1Mhz的计数时钟 
	TIM3->DIER|=1<<0;   // 允许更新中断 	    
	TIM3->CR1|=0x01;    // 使能定时器3 
	TIM3->ARR=20000; //20ms周期 = 20000us / 1us计数单位
	NVIC_InitStructure.NVIC_IRQChannel = TIM3_IRQn;  // TIM3中断 
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0;  // 先占优先级0级 
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1; 	 // 从优先级1级 
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE; // IRQ通道被使能 
	NVIC_Init(&NVIC_InitStructure);  // 根据NVIC_InitStruct中指定的参数初始化外设NVIC寄存器 
} 

void InitServo(void) 
{ 
	GPIO_InitTypeDef  GPIO_InitStructure; 
	InitTimer3(); 
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE); 
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_5; 
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP; 	 	  // 推挽输出 
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	GPIO_Init(GPIOB, &GPIO_InitStructure); 
	SERVO1 = 0;
} 

void Timer3ARRValue(uint16 pwm) 	 
{ 
	TIM3->ARR = pwm + 1; 
} 

void TIM3_IRQHandler(void) 
{ 	 	 
	static uint16 i = 1; 
	if(TIM3->SR&0X0001)// 溢出中断 
	{ 
		switch(i) 
		{ 
			case 1: 
				SERVO1 = 1; 	 
				Timer3ARRValue(ServoPwmDuty[0]); 
				break; 
			case 2: 
				SERVO1 = 0; 	 
				Timer3ARRValue(20000-ServoPwmDuty[0]); 	 
				break; 
		} 
		i++; 
		if(i > 2) 
			i = 1; 
	} 	 	 	    
	TIM3->SR&=~(1<<0);// 清除中断标志位 	     
} 
