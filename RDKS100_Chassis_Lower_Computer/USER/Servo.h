#ifndef _SERVO_H_
#define _SERVO_H_

#define SERVO1 PBout(5)			//转向舵机的控制

extern uint16 ServoPwmDutySet[];
extern uint16 ServoPwmDuty[];
extern bool ServoPwmDutyHaveChange;

void ServoSetPluseAndTime(uint8 id,uint16 p,uint16 time);
void ServoSetPluseImmediate(uint8 id,uint16 p);  // 立即设置舵机角度，无渐变
void ServoPwmDutyCompare(void);
void InitServo(void);

#endif
