#ifndef _ADC_H_
#define _ADC_H_

#define ADC_BAT		13		//电池电压的AD检测通道
#define BUZZER 		PCout(9)
#define LED PCout(15)
void InitADC(void);
void CheckBatteryVoltage(void);
u16 GetBatteryVoltage(void);
void Buzzer(void);
uint16 GetADCResult(BYTE ch);
void InitBuzzer(void);
void InitLED(void);

#endif
