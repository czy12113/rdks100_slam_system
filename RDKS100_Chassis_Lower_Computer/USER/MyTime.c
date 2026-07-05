#include "include.h"

u32 ServoCount;
extern uint8 BuzzerState;
extern bool ServoPwmDutyHaveChange;

void InitTimer2(void)		//100us
{
	NVIC_InitTypeDef NVIC_InitStructure;
	
	TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2, ENABLE); // 时钟使能

	TIM_TimeBaseStructure.TIM_Period = (10 - 1); // 设置在下一个更新事件装入活动的自动重装载寄存器周期的值
	TIM_TimeBaseStructure.TIM_Prescaler =(720-1); // 设置用来作为TIMx时钟频率除数的预分频值
	TIM_TimeBaseStructure.TIM_ClockDivision = 0; // 设置时钟分割:TDTS = Tck_tim
	TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;  // TIM向上计数模式
	TIM_TimeBaseInit(TIM2, &TIM_TimeBaseStructure); // 根据TIM_TimeBaseInitStruct中指定的参数初始化TIMx的时间基数单位

	TIM_ITConfig(  // 使能或者失能指定的TIM中断
	    TIM2, //TIM2
	    TIM_IT_Update  |  //TIM 中断源
	    TIM_IT_Trigger,   //TIM 触发中断源
	    ENABLE  // 使能
	);

	TIM_Cmd(TIM2, ENABLE);  // 使能TIMx外设
	
	NVIC_InitStructure.NVIC_IRQChannel = TIM2_IRQn;  // TIM2中断
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;  // 先占优先级0级
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 3;	// 从优先级3级
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE; // IRQ通道被使能
	NVIC_Init(&NVIC_InitStructure);  // 根据NVIC_InitStruct中指定的参数初始化外设NVIC寄存器
}

void TIM2_IRQHandler(void)   // TIM2中断
{// 定时器2中断  100us
	static uint32 time = 0;
	
	#ifdef USE_ROS2_PROTOCOL
	extern void ROS2_TimerCallback(void);
	#endif
	
	Buzzer();       // 蜂鸣器控制
	MotorPwmCtrl(); // 电机控制
	
	if(TIM_GetITStatus(TIM2, TIM_IT_Update) != RESET)  // 检查指定的TIM中断发生与否:TIM 中断源
	{
		TIM_ClearITPendingBit(TIM2, TIM_IT_Update);    // 清除TIMx的中断待处理位:TIM 中断源
		if(++time >= 10)
		{
			time = 0;
			ServoCount++;
			
			// ROS2 定时器回调 (每 1ms)
			#ifdef USE_ROS2_PROTOCOL
			ROS2_TimerCallback();
			#endif
		}
	}
}

void TaskTimeHandle(void)
{
	static uint32 time = 10;
	static uint32 times = 0;
	if(ServoCount > time)
	{
		//time += 10;
		times++;
		ServoCount= 0 ;
		if(times % 2 == 0)//20ms
		{
			ServoPwmDutyCompare();
		}
		if(times % 50 == 0)//500ms
		{
			CheckBatteryVoltage();  // 检测电压
			if(GetBatteryVoltage()<6400)
				BuzzerState = 1;        // 蜂鸣器标志位置1
			else
				BuzzerState = 0;        // 蜂鸣器标志位置0
		}
	}
}
