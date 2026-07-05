#include "include.h"

/*
 * 串口控制模块
 * 通过串口接收指令控制阿克曼底盘
 * 
 * 命令格式:
 * W    - 前进 (默认速度50)
 * S    - 后退 (默认速度40)
 * A    - 左转 (默认速度40, 转向70)
 * D    - 右转 (默认速度40, 转向70)
 * X    - 停止
 * Wxx  - 前进，速度xx (如 W50, W80)
 * Sxx  - 后退，速度xx
 * Axx  - 左转，转向程度xx (如 A70, A100)
 * Dxx  - 右转，转向程度xx
 * Txxxx - 设置舵机角度xxxx (如 T1500)
 */

// 默认参数
#define DEFAULT_FORWARD_SPEED   50
#define DEFAULT_BACKWARD_SPEED  40
#define DEFAULT_TURN_SPEED      40
#define DEFAULT_TURN_LEVEL      70

// 命令缓冲区
#define CMD_BUFFER_SIZE 8
static uint8 cmdBuffer[CMD_BUFFER_SIZE];
static uint8 cmdIndex = 0;
static uint8 controlMode = 0;  // 0: 自动模式, 1: 串口控制模式

// 串口控制初始化
void SerialControlInit(void)
{
    cmdIndex = 0;
    controlMode = 1;  // 默认启用串口控制
    printf("Serial Control Ready!\r\n");
    printf("Commands: W(forward) S(backward) A(left) D(right) X(stop)\r\n");
    printf("Example: W50 (forward speed 50), A70 (left turn level 70)\r\n");
}

// 解析并执行命令
static void ExecuteCommand(void)
{
    uint8 cmd = cmdBuffer[0];
    int16 param = 0;
    uint8 i;
    
    // 解析参数（如果有）
    if(cmdIndex > 1)
    {
        for(i = 1; i < cmdIndex; i++)
        {
            if(cmdBuffer[i] >= '0' && cmdBuffer[i] <= '9')
            {
                param = param * 10 + (cmdBuffer[i] - '0');
            }
        }
    }
    
    // 执行命令
    switch(cmd)
    {
        case 'W':  // 前进
        case 'w':
            if(param == 0) param = DEFAULT_FORWARD_SPEED;
            if(param > 100) param = 100;
            printf("Forward: speed=%d\r\n", param);
            AckermannGoStraight(param);
            break;
            
        case 'S':  // 后退
        case 's':
            if(param == 0) param = DEFAULT_BACKWARD_SPEED;
            if(param > 100) param = 100;
            printf("Backward: speed=%d\r\n", param);
            AckermannGoStraight(-param);
            break;
            
        case 'A':  // 左转
        case 'a':
            if(param == 0) param = DEFAULT_TURN_LEVEL;
            if(param > 100) param = 100;
            printf("Turn Left: level=%d\r\n", param);
            AckermannTurnLeft(DEFAULT_TURN_SPEED, param);
            break;
            
        case 'D':  // 右转
        case 'd':
            if(param == 0) param = DEFAULT_TURN_LEVEL;
            if(param > 100) param = 100;
            printf("Turn Right: level=%d\r\n", param);
            AckermannTurnRight(DEFAULT_TURN_SPEED, param);
            break;
            
        case 'X':  // 停止
        case 'x':
            printf("Stop\r\n");
            AckermannStop();
            break;
            
        case 'T':  // 设置舵机角度
        case 't':
            if(param >= 1000 && param <= 2000)
            {
                printf("Servo Angle: %d\r\n", param);
                AckermannSetSteeringAngle(param);
            }
            else
            {
                printf("Invalid angle (1000-2000)\r\n");
            }
            break;
            
        default:
            printf("Unknown command: %c\r\n", cmd);
            break;
    }
}

// 串口命令处理（在串口中断中调用）
void SerialControlProcess(uint8 data)
{
    // 回显接收到的字符
    // printf("%c", data);
    
    // 处理命令结束符
    if(data == '\r' || data == '\n')
    {
        if(cmdIndex > 0)
        {
            ExecuteCommand();
            cmdIndex = 0;  // 清空缓冲区
        }
        return;
    }
    
    // 存储命令字符
    if(cmdIndex < CMD_BUFFER_SIZE)
    {
        cmdBuffer[cmdIndex++] = data;
    }
    else
    {
        // 缓冲区溢出，重置
        printf("Command too long!\r\n");
        cmdIndex = 0;
    }
}

// 获取当前控制模式
uint8 SerialControlGetMode(void)
{
    return controlMode;
}
