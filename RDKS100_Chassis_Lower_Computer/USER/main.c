#include "include.h"
#include "ROS2Protocol.h"
#include "Odometry.h"
#include "ChassisParams.h"

static volatile uint8 control_task_flag = 0;
static volatile uint8 servo_task_flag = 0;
static volatile uint8 motor_task_flag = 0;
static volatile uint8 odom_update_flag = 0;
static volatile uint8 odom_send_flag = 0;

void ROS2_TimerCallback(void)
{
    static uint16 control_counter = 0;
    static uint16 servo_counter = 0;
    static uint16 motor_counter = 0;
    static uint16 odom_update_counter = 0;
    static uint16 odom_send_counter = 0;

    ROS2Protocol_1msTick();

    control_counter++;
    servo_counter++;
    motor_counter++;
    odom_update_counter++;
    odom_send_counter++;

    if(control_counter >= CONTROL_TASK_PERIOD_MS)
    {
        control_counter = 0;
        control_task_flag = 1;
    }

    if(servo_counter >= SERVO_TASK_PERIOD_MS)
    {
        servo_counter = 0;
        servo_task_flag = 1;
    }

    if(motor_counter >= MOTOR_TASK_PERIOD_MS)
    {
        motor_counter = 0;
        motor_task_flag = 1;
    }

    if(odom_update_counter >= ODOM_UPDATE_PERIOD_MS)
    {
        odom_update_counter = 0;
        odom_update_flag = 1;
    }

    if(odom_send_counter >= ODOM_SEND_PERIOD_MS)
    {
        odom_send_counter = 0;
        odom_send_flag = 1;
    }
}

static void SendOdomFrame(void)
{
    Odometry_t odom;
    int32 pos_x_mm;
    int32 pos_y_mm;
    int16 yaw_mrad;
    int16 linear_vel_mms;
    int16 angular_vel_mrads;

#if (!ODOMETRY_READ_ENCODER) && (!ODOM_SEND_WITHOUT_ENCODER)
    /* Encoder reads are disabled and we are not allowed to publish synthetic
     * odom. Bail out so the upper computer falls back to its open-loop
     * integrator instead of consuming an all-zero frame that would zero the
     * UI velocity bars and freeze Nav2 / AMCL on a stale pose.
     */
    return;
#else
    if(!Odometry_IsValid())
    {
        /* Encoder I/O is failing; do not advertise stale data to ROS2. */
        return;
    }

    Odometry_GetData(&odom);

    pos_x_mm = (int32)(odom.pos_x * 1000.0f);
    pos_y_mm = (int32)(odom.pos_y * 1000.0f);
    yaw_mrad = (int16)(odom.yaw * 1000.0f);
    linear_vel_mms = (int16)(odom.linear_vel * 1000.0f);
    angular_vel_mrads = (int16)(odom.angular_vel * 1000.0f);

#if DEBUG_PROTOCOL_UART
    printf("Odom: x=%d y=%d yaw=%d\r\n", pos_x_mm, pos_y_mm, yaw_mrad);
#endif

    ROS2Protocol_SendOdom(pos_x_mm, pos_y_mm, yaw_mrad,
                          linear_vel_mms, angular_vel_mrads);
#endif
}

int main(void)
{
    SystemInit();
    NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);
    InitDelay(72);
    InitTimer2();
    IIC_init();
    Usart1_Init();
    InitLED();
    DelayMs(200);

    AckermannInit();
    ROS2Protocol_Init();
    Odometry_Init();

#if DEBUG_PROTOCOL_UART
    printf("\r\n=== ROS2 Ackermann Chassis Control ===\r\n");
    printf("Wheelbase: %.3f m\r\n", WHEELBASE);
    printf("Track Width: %.3f m\r\n", TRACK_WIDTH);
    printf("Wheel Diameter: %.3f m\r\n", WHEEL_DIAMETER);
    printf("Max Linear Speed: %.2f m/s\r\n", MAX_LINEAR_SPEED);
    printf("Max Angular Speed: %.2f rad/s\r\n", MAX_ANGULAR_SPEED);
    printf("Waiting for ROS2 commands...\r\n\r\n");
#endif

    while(1)
    {
        if(control_task_flag)
        {
            control_task_flag = 0;
            ROS2Protocol_Task();
        }

        if(motor_task_flag)
        {
            motor_task_flag = 0;
            AckermannTask();
        }

        if(servo_task_flag)
        {
            servo_task_flag = 0;
            ServoPwmDutyCompare();
        }

#if ODOMETRY_READ_ENCODER
        if(odom_update_flag)
        {
            odom_update_flag = 0;
            Odometry_Update();
        }
#else
        odom_update_flag = 0;
#endif

        if(odom_send_flag)
        {
            odom_send_flag = 0;
            SendOdomFrame();
        }
    }
}
