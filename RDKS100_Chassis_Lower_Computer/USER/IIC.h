#ifndef __IIC_H
#define __IIC_H

//*****软件模拟IIC*****
//*****修改引脚定义*****
//*****不同芯片时注意时序调整*****
#define    IIC_IO_SDA      GPIO_Pin_7  //SDA引脚
#define    IIC_IO_SCL      GPIO_Pin_6  //SCL引脚
#define    GPIOX           GPIOB       //GPIOx选择
#define    CLOCK		   RCC_APB2Periph_GPIOB //时钟使能
 
#define    IIC_SCL         PBout(6) //SCL
#define    IIC_SDA         PBout(7) //输出SDA
#define    READ_SDA        PBin(7)  //读取SDA


void I2C_SDA_OUT(void);
void I2C_SDA_IN(void);
void IIC_init(void);
void IIC_start(void);
void IIC_stop(void);
void IIC_ack(void);
void IIC_noack(void);
u8 IIC_wait_ack(void);
void IIC_send_byte(u8 txd);
u8 IIC_read_byte(u8 ack);
#endif
