#include "include.h"

uint8 BuzzerState = 0;
uint16 BatteryVoltage;

void InitLED(void)
{

	GPIO_InitTypeDef  GPIO_InitStructure;

	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);	 // 使能PB端口时钟
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_15;				 
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP; 		 // 推挽输出
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOC, &GPIO_InitStructure);

}
void InitBuzzer(void)
{

	GPIO_InitTypeDef  GPIO_InitStructure;

	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);	 // 使能端口时钟

	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9;				 
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP; 		 // 推挽输出
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOC, &GPIO_InitStructure);

}

void InitADC(void)
{
	ADC_InitTypeDef ADC_InitStructure;
	GPIO_InitTypeDef GPIO_InitStructure;
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC |RCC_APB2Periph_ADC1	, ENABLE);	   // 使能ADC1通道时钟

	RCC_ADCCLKConfig(RCC_PCLK2_Div6);   //72M/6=12,ADC最大时钟不能超过14M
	//PA0/1/2/3 作为模拟通道输入引脚
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_3;//|GPIO_Pin_1|GPIO_Pin_2|GPIO_Pin_3;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AIN;		// 模拟输入引脚
	GPIO_Init(GPIOC, &GPIO_InitStructure);

	ADC_DeInit(ADC1);  // 复位外设 ADC1 的全部寄存器至缺省值

	ADC_InitStructure.ADC_Mode = ADC_Mode_Independent;	// ADC工作模式:ADC1和ADC2工作在独立模式
	ADC_InitStructure.ADC_ScanConvMode = DISABLE;	// 模数转换工作在单通道模式
	ADC_InitStructure.ADC_ContinuousConvMode = DISABLE;	// 模数转换工作在单次转换模式
	ADC_InitStructure.ADC_ExternalTrigConv = ADC_ExternalTrigConv_None;	// 转换由软件而不是外部触发启动
	ADC_InitStructure.ADC_DataAlign = ADC_DataAlign_Right;	// ADC数据右对齐
	ADC_InitStructure.ADC_NbrOfChannel = 1;	// 顺序进行规则转换的ADC通道的数目
	ADC_Init(ADC1, &ADC_InitStructure);	// 根据ADC_InitStruct中指定的参数初始化外设ADCx的寄存器



	ADC_Cmd(ADC1, ENABLE);	// 使能指定的ADC1

	ADC_ResetCalibration(ADC1);	// 复位指定的ADC1的校准寄存器

	while(ADC_GetResetCalibrationStatus(ADC1));	// 获取ADC1复位校准寄存器的状态,设置状态则等待

	ADC_StartCalibration(ADC1);		// 开始指定ADC1的校准状态

	while(ADC_GetCalibrationStatus(ADC1));		// 获取指定ADC1的校准程序,设置状态则等待

	ADC_SoftwareStartConvCmd(ADC1, ENABLE);		// 使能指定的ADC1的软件转换启动功能
}


uint16 GetADCResult(BYTE ch)
{
	// 设置指定ADC的规则组通道，设置它们的转换顺序和采样时间
	ADC_RegularChannelConfig(ADC1, ch, 1, ADC_SampleTime_239Cycles5);	//ADC1,ADC通道3,规则采样顺序值为1,采样时间为239.5周期

	ADC_SoftwareStartConvCmd(ADC1, ENABLE);		// 使能指定的ADC1的软件转换启动功能

	while(!ADC_GetFlagStatus(ADC1, ADC_FLAG_EOC)); // 等待转换结束

	return ADC_GetConversionValue(ADC1);	// 返回最近一次ADC1规则组的转换结果
}


void CheckBatteryVoltage(void)
{
	uint8 i;
	uint32 v = 0;
	for(i = 0;i < 8;i++)
	{
		v += GetADCResult(ADC_BAT);
	}
	v >>= 3;
	
	v = v * 2475 / 1024;//adc / 4096 * 3300 * 3(3倍放大3倍是因为采集电压时，将电压除3)
	BatteryVoltage = v;

}

uint16 GetBatteryVoltage(void)
{// 电压检测
	return BatteryVoltage;
}

void Buzzer(void)
{// 放到100us的定时中断里面
	static bool fBuzzer = FALSE;
	static uint32 t1 = 0;
	static uint32 t2 = 0;
	if(fBuzzer)
	{
		if(++t1 >= 2)
		{
			t1 = 0;
			BUZZER = !BUZZER;//2.5KHz
		}
	}
	else
	{
		BUZZER = 0;
	}

	
	if(BuzzerState == 0)
	{
		fBuzzer = FALSE;
		t2 = 0;
	}
	else if(BuzzerState == 1)
	{
		t2++;
		if(t2 < 5000)
		{
			fBuzzer = TRUE;
		}
		else if(t2 < 10000)
		{
			fBuzzer = FALSE;
		}
		else
		{
			t2 = 0;
		}
	}
}


