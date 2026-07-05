#ifndef __USART_H_
#define __USART_H_
#include<stdio.h>

void Usart1_Init(void);
void Usart_SendByte(USART_TypeDef* USARTx, uint8 data);

#endif
