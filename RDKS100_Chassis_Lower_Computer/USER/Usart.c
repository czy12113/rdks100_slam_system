#include "include.h"

#ifndef DEBUG_PROTOCOL_UART
#define DEBUG_PROTOCOL_UART 0
#endif

#pragma import(__use_no_semihosting)             
// 标准库需要的支持函数                 
struct __FILE 
{ 
	int handle; 
}; 
FILE __stdout;       
// 定义_sys_exit()以避免使用半主机模式    
void _sys_exit(int x) 
{ 
	x = x; 
} 
// 重定向printf到USART1
int fputc(int ch, FILE *f)
{
#if DEBUG_PROTOCOL_UART
USART_SendData(USART1, (uint8_t) ch);
while (USART_GetFlagStatus(USART1, USART_FLAG_TC) == RESET);
#else
ch = ch;
f = f;
#endif
return (ch);
}


void Usart1_Init(void)
{
	NVIC_InitTypeDef NVIC_InitStructure;
	
	GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
//	NVIC_InitTypeDef NVIC_InitStructure;

	RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1|RCC_APB2Periph_GPIOA|RCC_APB2Periph_AFIO, ENABLE);
	//USART1_TX   PA.9
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
	GPIO_Init(GPIOA, &GPIO_InitStructure);

	//USART1_RX	  PA.10
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
	GPIO_Init(GPIOA, &GPIO_InitStructure);

	// USART 初始化设置

	USART_InitStructure.USART_BaudRate = 115200;
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;
	USART_InitStructure.USART_StopBits = USART_StopBits_1;
	USART_InitStructure.USART_Parity = USART_Parity_No;
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;

	USART_Init(USART1, &USART_InitStructure);

	USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);// 开启中断

	USART_Cmd(USART1, ENABLE);                    // 使能串口
	
	
	NVIC_InitStructure.NVIC_IRQChannel = USART1_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority=1 ;
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0;		//
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;			// IRQ通道使能
	NVIC_Init(&NVIC_InitStructure);	// 根据NVIC_InitStruct中指定的参数初始化外设NVIC寄存器USART1
}

void USART1_IRQHandler(void)
{
	uint8 ch;
	
	if(USART_GetITStatus(USART1, USART_IT_RXNE) != RESET) 
	{
		ch = USART_ReceiveData(USART1);
		
#ifdef USE_ROS2_PROTOCOL
		// ROS2协议模式：逐字节处理
		ROS2Protocol_ProcessByte(ch);
#else
		// 简单串口控制模式
		SerialControlProcess(ch);
#endif
	}
}

// 发送单个字节（ROS2协议需要）
void Usart_SendByte(USART_TypeDef* USARTx, uint8 data)
{
	USART_SendData(USARTx, data);
	while(USART_GetFlagStatus(USARTx, USART_FLAG_TC) == RESET);
}
