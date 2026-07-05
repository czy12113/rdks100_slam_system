#include "include.h"

void I2C_SDA_OUT(void)// SDA设置为推挽输出
{
  GPIO_InitTypeDef GPIO_InitStructure;	
	//RCC_APB2PeriphClockCmd(CLOCK,ENABLE);
	GPIO_InitStructure.GPIO_Pin=IIC_IO_SDA;
	GPIO_InitStructure.GPIO_Speed=GPIO_Speed_50MHz;
	GPIO_InitStructure.GPIO_Mode=GPIO_Mode_Out_PP;// SDA推挽输出
	GPIO_Init(GPIOX,&GPIO_InitStructure); 						
}

void I2C_SDA_IN(void)// SDA设置为上拉输入
{
	GPIO_InitTypeDef GPIO_InitStructure;	
	//RCC_APB2PeriphClockCmd(CLOCK,ENABLE);
	GPIO_InitStructure.GPIO_Pin=IIC_IO_SDA;
	GPIO_InitStructure.GPIO_Speed=GPIO_Speed_50MHz;
	GPIO_InitStructure.GPIO_Mode=GPIO_Mode_IPU;// SCL上拉输入
	GPIO_Init(GPIOX,&GPIO_InitStructure);
}

// 软件模拟IIC高速率
void IIC_init()
{
	GPIO_InitTypeDef  GPIO_InitStructure;
	RCC_APB2PeriphClockCmd(CLOCK, ENABLE);	 // 启用PB端口时钟
	GPIO_InitStructure.GPIO_Pin = IIC_IO_SDA |IIC_IO_SCL;	// PB6和PB7设置为推挽输出,SCL
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP; 		
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;		 // IO速度为50MHz
	GPIO_Init(GPIOX, &GPIO_InitStructure);					 // 设置并初始化GPIOB
	GPIO_SetBits(GPIOX,IIC_IO_SDA|IIC_IO_SCL); 
}

void IIC_start()	// 起始信号
{
	I2C_SDA_OUT();
	IIC_SDA=1;	  	  
	IIC_SCL=1;
	DelayUs(5);
	IIC_SDA=0;
	DelayUs(5);
	IIC_SCL=0;
}

void IIC_stop()		// 停止信号
{
	I2C_SDA_OUT();
	IIC_SCL=0;
	IIC_SDA=0;
	DelayUs(5);
	IIC_SCL=1; 
	IIC_SDA=1;
	DelayUs(5);
}

// 产生一个应答信号
void IIC_ack()
{
	IIC_SCL=0;
	I2C_SDA_OUT();
  IIC_SDA=0;	
  DelayUs(2);
  IIC_SCL=1;
  DelayUs(2);
  IIC_SCL=0;	
}

// 产生一个非应答信号
void IIC_noack()
{
	IIC_SCL=0;
	I2C_SDA_OUT();
  IIC_SDA=1;
  DelayUs(2);
  IIC_SCL=1;
  DelayUs(2);
  IIC_SCL=0;
}

// 等待应答信号
// 返回值:1 应答失败
//		  0 应答成功
u8 IIC_wait_ack()
{
	u8 tempTime=0;
	I2C_SDA_IN();
	IIC_SDA=1;
	DelayUs(1);
	IIC_SCL=1;
	DelayUs(1);

	while(READ_SDA)
	{
		tempTime++;
		if(tempTime>250)
		{
			IIC_stop();
			return 1;
		}	 
	}

	IIC_SCL=0;
	return 0;
}

void IIC_send_byte(u8 txd)
{
	u8 i=0;
	I2C_SDA_OUT();
	IIC_SCL=0;;// 时钟线置低开始传输数据
	for(i=0;i<8;i++)
	{
		IIC_SDA=(txd&0x80)>>7;// 提取字节
		txd<<=1;
		DelayUs(2);
		IIC_SCL=1;
		DelayUs(2); // 建立时间
		IIC_SCL=0;
		DelayUs(2);
	}
}



// 读取一个字节
u8 IIC_read_byte(u8 ack)
{
	u8 i=0,receive=0;
	I2C_SDA_IN();
  for(i=0;i<8;i++)
  {
   	IIC_SCL=0;
		DelayUs(2);
		IIC_SCL=1;
		receive<<=1;// 左移
		if(READ_SDA)
		   receive++;// 读取该位
		DelayUs(1);	
  }

  if(!ack)
	  IIC_noack();
	else
		IIC_ack();

	return receive;// 返回读取的字节
}
