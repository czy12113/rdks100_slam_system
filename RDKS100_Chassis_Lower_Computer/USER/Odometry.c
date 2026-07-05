#include "include.h"
#include "Odometry.h"
#include "ChassisParams.h"
#include "AckermannControl.h"
#include "I2CMotor.h"
#include <math.h>

extern u32 ServoCount;

static Odometry_t odom;

static int32 encoder_left = 0;
static int32 encoder_right = 0;
static int32 encoder_left_last = 0;
static int32 encoder_right_last = 0;

static uint32 last_update_time = 0;

/* Health tracking for the encoder read path. odom_valid is consumed by
 * Odometry_IsValid() so the main loop can choose not to publish a stale
 * frame, and the open-loop integrator in stm32_bridge.py takes over.
 */
static uint8 odom_valid = 0;
static uint8 encoder_fail_streak = 0;

/* Returns:
 *   0 = success, encoder values updated
 *   1 = transfer error (or feature disabled), caller should treat this tick
 *       as a miss
 *   2 = bus busy with a motor write, caller should silently skip this tick
 *       without flipping the valid flag (it is not really a failure, just a
 *       deferral, but we still bump the streak so a sustained busy bus
 *       eventually drops odom_valid)
 */
static uint8 Odometry_ReadEncoderCount(void)
{
#if ODOMETRY_READ_ENCODER
    int32_t encoder[4];
    int32 left_count;
    int32 right_count;
    uint8_t status;

    status = I2CMotor_ReadEncoder(encoder);
    if(status != 0)
    {
        return status;
    }

    /* Two motors on each side; average them to get a single per-side count.
     * Indices match I2CMotor_SetSpeedIndividual: 0=LF, 1=RF, 2=LR, 3=RR.
     */
    left_count = (int32)((encoder[0] + encoder[2]) / 2);
    right_count = (int32)((encoder[1] + encoder[3]) / 2);

    encoder_left = left_count;
    encoder_right = right_count;

    return 0;
#else
    return 1;
#endif
}

void Odometry_Init(void)
{
    odom.pos_x = 0.0f;
    odom.pos_y = 0.0f;
    odom.yaw = 0.0f;
    odom.linear_vel = 0.0f;
    odom.angular_vel = 0.0f;
    odom.timestamp = 0;

    encoder_left = 0;
    encoder_right = 0;
    odom_valid = 0;
    encoder_fail_streak = 0;

    if(Odometry_ReadEncoderCount() == 0)
    {
        encoder_left_last = encoder_left;
        encoder_right_last = encoder_right;
        odom_valid = 1;
    }
    else
    {
        encoder_left_last = 0;
        encoder_right_last = 0;
    }

    last_update_time = ServoCount;

#if DEBUG_PROTOCOL_UART
    printf("Odometry Initialized (read=%d, ackermann_model=%d)\r\n",
           ODOMETRY_READ_ENCODER, ODOM_USE_ACKERMANN_MODEL);
#endif
}

void Odometry_Update(void)
{
    uint32 current_time;
    float dt;
    int32 delta_left;
    int32 delta_right;
    float dist_left;
    float dist_right;
    float dist_center;
    float delta_yaw;
    float mid_yaw;
    uint8 read_status;
#if ODOM_USE_ACKERMANN_MODEL
    float steering_angle;
#endif

    current_time = ServoCount;
    dt = (current_time - last_update_time) / 1000.0f;

    if(dt < 0.001f)
    {
        return;
    }

    read_status = Odometry_ReadEncoderCount();
    if(read_status != 0)
    {
        /* Do not zero linear_vel / angular_vel here. The previous version
         * forced them to 0 on every miss, which made odom_valid look fine
         * to consumers while actually publishing 0 velocity — that
         * masquerades as "the car has stopped" and is exactly the kind of
         * lie that causes Nav2 / AMCL drift.
         */
        if(encoder_fail_streak < 0xFF)
        {
            encoder_fail_streak++;
        }
        if(encoder_fail_streak >= ODOM_ENCODER_FAIL_LIMIT)
        {
            odom_valid = 0;
        }
        last_update_time = current_time;
        return;
    }

    encoder_fail_streak = 0;

    delta_left = encoder_left - encoder_left_last;
    delta_right = encoder_right - encoder_right_last;

    dist_left = (delta_left / (ENCODER_PPR * GEAR_RATIO)) *
                (2.0f * PI * WHEEL_RADIUS);
    dist_right = (delta_right / (ENCODER_PPR * GEAR_RATIO)) *
                 (2.0f * PI * WHEEL_RADIUS);

    dist_center = (dist_left + dist_right) / 2.0f;

#if ODOM_USE_ACKERMANN_MODEL
    /* Bicycle / Ackermann kinematics:
     *
     *   delta_yaw = dist_center * tan(steering_angle) / WHEELBASE
     *
     * This is the correct model for a chassis with two rear-drive wheels
     * and a steered front axle. The previous differential formula
     *   delta_yaw = (dist_right - dist_left) / TRACK_WIDTH
     * is wrong here: both rear wheels normally turn at the same speed, so
     * delta_yaw collapses to 0 even when the car is actively cornering.
     * The result is an odom that never registers heading change while the
     * pose still translates, which is the classic Nav2 drift signature.
     */
    steering_angle = AckermannGetSteeringAngleRad();
    if(fabsf(steering_angle) < 1e-4f)
    {
        delta_yaw = 0.0f;
    }
    else
    {
        delta_yaw = dist_center * tanf(steering_angle) / WHEELBASE;
    }
#else
    delta_yaw = (dist_right - dist_left) / TRACK_WIDTH;
#endif

    odom.linear_vel = dist_center / dt;
    odom.angular_vel = delta_yaw / dt;

    mid_yaw = odom.yaw + (delta_yaw / 2.0f);
    odom.pos_x += dist_center * cosf(mid_yaw);
    odom.pos_y += dist_center * sinf(mid_yaw);

    odom.yaw += delta_yaw;
    while(odom.yaw > PI)
    {
        odom.yaw -= 2.0f * PI;
    }
    while(odom.yaw < -PI)
    {
        odom.yaw += 2.0f * PI;
    }

    odom.timestamp = current_time;
    encoder_left_last = encoder_left;
    encoder_right_last = encoder_right;
    last_update_time = current_time;
    odom_valid = 1;
}

void Odometry_GetData(Odometry_t* odom_out)
{
    odom_out->pos_x = odom.pos_x;
    odom_out->pos_y = odom.pos_y;
    odom_out->yaw = odom.yaw;
    odom_out->linear_vel = odom.linear_vel;
    odom_out->angular_vel = odom.angular_vel;
    odom_out->timestamp = odom.timestamp;
}

void Odometry_GetDataROS2(int32* pos_x, int32* pos_y, int16* yaw,
                          int16* linear_vel, int16* angular_vel)
{
    *pos_x = (int32)(odom.pos_x * 1000.0f);
    *pos_y = (int32)(odom.pos_y * 1000.0f);
    *yaw = (int16)(odom.yaw * 1000.0f);
    *linear_vel = (int16)(odom.linear_vel * 1000.0f);
    *angular_vel = (int16)(odom.angular_vel * 1000.0f);
}

void Odometry_Reset(void)
{
    odom.pos_x = 0.0f;
    odom.pos_y = 0.0f;
    odom.yaw = 0.0f;
    odom.linear_vel = 0.0f;
    odom.angular_vel = 0.0f;
    odom.timestamp = ServoCount;

    encoder_left = 0;
    encoder_right = 0;
    encoder_fail_streak = 0;

    if(Odometry_ReadEncoderCount() == 0)
    {
        encoder_left_last = encoder_left;
        encoder_right_last = encoder_right;
        odom_valid = 1;
    }
    else
    {
        encoder_left_last = 0;
        encoder_right_last = 0;
        odom_valid = 0;
    }

    last_update_time = ServoCount;
}

void Odometry_SetEncoderCount(int32 left_count, int32 right_count)
{
    encoder_left = left_count;
    encoder_right = right_count;
}

uint8 Odometry_IsValid(void)
{
#if ODOMETRY_READ_ENCODER
    return odom_valid;
#else
    /* No encoders -> no real odom. Returning 0 here, combined with the
     * SendOdomFrame() guard in main.c, makes the firmware silent on the
     * odom uplink, so the upper computer's open-loop integrator owns the
     * /odom topic and TF.
     */
    return 0;
#endif
}
