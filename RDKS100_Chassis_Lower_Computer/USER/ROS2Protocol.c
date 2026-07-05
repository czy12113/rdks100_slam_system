#include "include.h"
#include "ROS2Protocol.h"
#include "ChassisParams.h"
#include <math.h>

#define RX_BUFFER_SIZE 32

static uint8 rxBuffer[RX_BUFFER_SIZE];
static uint8 rxIndex = 0;
static uint8 rxState = 0;

static volatile ControlCmd_t pendingCmd;
static volatile uint8 pendingCmdValid = 0;
static volatile uint16 cmdTimeoutCounter = 0;
static volatile uint8 cmdWatchdogEnabled = 0;
static volatile uint8 cmdTimeoutStopPending = 0;

static void QueueControlCmd(ControlCmd_t* cmd);
static uint8 TakePendingCmd(ControlCmd_t* cmd);
static void CopyCmdToPending(ControlCmd_t* cmd);
static void CopyPendingToCmd(ControlCmd_t* cmd);
static void ProcessControlCmd(ControlCmd_t* cmd);
static void MarkControlFrameReceived(uint8 motion_active);
static uint16 SteeringAngleToServoPulse(float angle_rad);
static int8 LinearVelToMotorSpeed(float vel_ms);
static float ClampFloat(float value, float min_value, float max_value);

void ROS2Protocol_Init(void)
{
    rxIndex = 0;
    rxState = 0;
    pendingCmdValid = 0;
    cmdTimeoutCounter = 0;
    cmdWatchdogEnabled = 0;
    cmdTimeoutStopPending = 0;

#if DEBUG_PROTOCOL_UART
    printf("ROS2 Protocol Initialized\r\n");
#endif
}

void ROS2Protocol_1msTick(void)
{
    if(cmdWatchdogEnabled)
    {
        if(cmdTimeoutCounter < CMD_TIMEOUT_MS)
        {
            cmdTimeoutCounter++;
        }

        if(cmdTimeoutCounter >= CMD_TIMEOUT_MS)
        {
            cmdWatchdogEnabled = 0;
            cmdTimeoutStopPending = 1;
        }
    }
}

uint8 ROS2Protocol_TakeTimeoutStop(void)
{
    if(cmdTimeoutStopPending)
    {
        cmdTimeoutStopPending = 0;
        return 1;
    }

    return 0;
}

void ROS2Protocol_Task(void)
{
    ControlCmd_t cmd;

    if(TakePendingCmd(&cmd))
    {
        ProcessControlCmd(&cmd);
        return;
    }

    if(ROS2Protocol_TakeTimeoutStop())
    {
        AckermannStop();
    }
}

uint8 ROS2Protocol_CalcChecksum(uint8* data, uint8 len)
{
    uint8 sum;
    uint8 i;

    sum = 0;
    for(i = 0; i < len; i++)
    {
        sum += data[i];
    }

    return sum;
}

void ROS2Protocol_ProcessByte(uint8 data)
{
    ControlCmd_t* cmd;
    uint8 calc_sum;

    switch(rxState)
    {
        case 0:
            if(rxIndex == 0 && data == FRAME_HEADER_0)
            {
                rxBuffer[rxIndex++] = data;
            }
            else if(rxIndex == 1 && data == FRAME_HEADER_1)
            {
                rxBuffer[rxIndex++] = data;
                rxState = 1;
            }
            else
            {
                rxIndex = 0;
            }
            break;

        case 1:
            rxBuffer[rxIndex++] = data;

            if(rxIndex >= sizeof(ControlCmd_t))
            {
                cmd = (ControlCmd_t*)rxBuffer;

                if(cmd->tail == FRAME_TAIL)
                {
                    calc_sum = ROS2Protocol_CalcChecksum(rxBuffer + 2,
                                                         sizeof(ControlCmd_t) - 4);
                    if(calc_sum == cmd->checksum)
                    {
                        QueueControlCmd(cmd);
                    }
                }

                rxIndex = 0;
                rxState = 0;
            }

            if(rxIndex >= RX_BUFFER_SIZE)
            {
                rxIndex = 0;
                rxState = 0;
            }
            break;

        default:
            rxIndex = 0;
            rxState = 0;
            break;
    }
}

static void QueueControlCmd(ControlCmd_t* cmd)
{
    CopyCmdToPending(cmd);
    pendingCmdValid = 1;
}

static uint8 TakePendingCmd(ControlCmd_t* cmd)
{
    uint8 has_cmd;

    has_cmd = 0;
    NVIC_DisableIRQ(USART1_IRQn);
    if(pendingCmdValid)
    {
        CopyPendingToCmd(cmd);
        pendingCmdValid = 0;
        has_cmd = 1;
    }
    NVIC_EnableIRQ(USART1_IRQn);

    return has_cmd;
}

static void CopyCmdToPending(ControlCmd_t* cmd)
{
    uint8 i;
    uint8* src;
    volatile uint8* dst;

    src = (uint8*)cmd;
    dst = (volatile uint8*)&pendingCmd;

    for(i = 0; i < sizeof(ControlCmd_t); i++)
    {
        dst[i] = src[i];
    }
}

static void CopyPendingToCmd(ControlCmd_t* cmd)
{
    uint8 i;
    volatile uint8* src;
    uint8* dst;

    src = (volatile uint8*)&pendingCmd;
    dst = (uint8*)cmd;

    for(i = 0; i < sizeof(ControlCmd_t); i++)
    {
        dst[i] = src[i];
    }
}

static void ProcessControlCmd(ControlCmd_t* cmd)
{
    float linear_vel;
    float angular_vel;
    float steering_angle;
    uint16 servo_pulse;
    int8 motor_speed;

    switch(cmd->cmd_type)
    {
        case CMD_VELOCITY:
            linear_vel = cmd->linear_vel / 1000.0f;
            angular_vel = cmd->angular_vel / 1000.0f;

            linear_vel = ClampFloat(linear_vel, -MAX_LINEAR_SPEED, MAX_LINEAR_SPEED);
            angular_vel = ClampFloat(angular_vel, -MAX_ANGULAR_SPEED, MAX_ANGULAR_SPEED);

            if(fabs(linear_vel) < LINEAR_DEADBAND)
            {
                linear_vel = 0.0f;
            }
            if(fabs(angular_vel) < ANGULAR_DEADBAND)
            {
                angular_vel = 0.0f;
            }

            MarkControlFrameReceived((linear_vel != 0.0f) || (angular_vel != 0.0f));

            if(linear_vel == 0.0f && angular_vel == 0.0f)
            {
                AckermannStop();
                break;
            }

            steering_angle = 0.0f;
            if(fabs(angular_vel) > ANGULAR_DEADBAND)
            {
                if(fabs(linear_vel) > LINEAR_DEADBAND)
                {
                    steering_angle = atan2f(angular_vel * WHEELBASE, fabs(linear_vel));
                }
                else
                {
                    steering_angle = angular_vel * MAX_STEERING_ANGLE / MAX_ANGULAR_SPEED;
                }

                steering_angle = ClampFloat(steering_angle,
                                            -MAX_STEERING_ANGLE,
                                            MAX_STEERING_ANGLE);
            }

            servo_pulse = SteeringAngleToServoPulse(steering_angle);
            motor_speed = LinearVelToMotorSpeed(linear_vel);
            AckermannTurn(motor_speed, servo_pulse);
            break;

        case CMD_STOP:
            MarkControlFrameReceived(0);
            AckermannStop();
            break;

        case CMD_RESET:
            MarkControlFrameReceived(0);
            AckermannStop();
            Odometry_Reset();
            break;

        case CMD_GET_ODOM:
            break;

        default:
            break;
    }
}

static void MarkControlFrameReceived(uint8 motion_active)
{
    cmdTimeoutCounter = 0;
    cmdTimeoutStopPending = 0;
    cmdWatchdogEnabled = motion_active ? 1 : 0;
}

static uint16 SteeringAngleToServoPulse(float angle_rad)
{
    float normalized;
    int16 offset;
    uint16 pulse;

    normalized = angle_rad / MAX_STEERING_ANGLE;

    if(normalized >= 0.0f)
    {
        offset = (int16)(normalized * (SERVO_LEFT_MAX - SERVO_CENTER_ANGLE));
    }
    else
    {
        offset = (int16)(normalized * (SERVO_CENTER_ANGLE - SERVO_RIGHT_MAX));
    }

    pulse = SERVO_CENTER_ANGLE + offset;

    if(pulse < SERVO_LEFT_MAX)
    {
        pulse = SERVO_LEFT_MAX;
    }
    if(pulse > SERVO_RIGHT_MAX)
    {
        pulse = SERVO_RIGHT_MAX;
    }

    return pulse;
}

static int8 LinearVelToMotorSpeed(float vel_ms)
{
    int16 speed;

    speed = (int16)((vel_ms / MAX_LINEAR_SPEED) * 100.0f);

    if(speed > 100)
    {
        speed = 100;
    }
    if(speed < -100)
    {
        speed = -100;
    }

    return (int8)speed;
}

static float ClampFloat(float value, float min_value, float max_value)
{
    if(value > max_value)
    {
        return max_value;
    }
    if(value < min_value)
    {
        return min_value;
    }

    return value;
}

void ROS2Protocol_SendOdom(int32 pos_x, int32 pos_y, int16 yaw,
                           int16 linear_vel, int16 angular_vel)
{
    OdomData_t odom;
    uint8* data;
    uint8 i;

    odom.header[0] = ODOM_HEADER_0;
    odom.header[1] = ODOM_HEADER_1;
    odom.data_type = DATA_TYPE_ODOM;
    odom.pos_x = pos_x;
    odom.pos_y = pos_y;
    odom.yaw = yaw;
    odom.linear_vel = linear_vel;
    odom.angular_vel = angular_vel;
    odom.reserved = 0x00;
    odom.checksum = ROS2Protocol_CalcChecksum(((uint8*)&odom) + 2,
                                              sizeof(OdomData_t) - 4);
    odom.tail = FRAME_TAIL;

    data = (uint8*)&odom;
    for(i = 0; i < sizeof(OdomData_t); i++)
    {
        Usart_SendByte(USART1, data[i]);
    }
}

void ROS2Protocol_SendStatus(uint8 battery, int16 current,
                             uint16 error, uint8 status)
{
    StatusData_t stat;
    uint8* data;
    uint8 i;

    stat.header[0] = ODOM_HEADER_0;
    stat.header[1] = ODOM_HEADER_1;
    stat.data_type = DATA_TYPE_STATUS;
    stat.battery_level = battery;
    stat.motor_current = current;
    stat.error_code = error;
    stat.status = status;
    stat.checksum = ROS2Protocol_CalcChecksum(((uint8*)&stat) + 2,
                                              sizeof(StatusData_t) - 4);
    stat.tail = FRAME_TAIL;

    data = (uint8*)&stat;
    for(i = 0; i < sizeof(StatusData_t); i++)
    {
        Usart_SendByte(USART1, data[i]);
    }
}
