#ifndef _ODOMETRY_H_
#define _ODOMETRY_H_

#include "include.h"

typedef struct {
    float pos_x;
    float pos_y;
    float yaw;
    float linear_vel;
    float angular_vel;
    uint32 timestamp;
} Odometry_t;

void Odometry_Init(void);
void Odometry_Update(void);
void Odometry_GetData(Odometry_t* odom);
void Odometry_GetDataROS2(int32* pos_x, int32* pos_y, int16* yaw,
                          int16* linear_vel, int16* angular_vel);
void Odometry_Reset(void);
void Odometry_SetEncoderCount(int32 left_count, int32 right_count);

/* Returns non-zero when the most recent encoder read succeeded and the
 * integrated pose is fresh. Returns 0 if encoders are disabled, the I2C bus
 * has been busy for too long, or the encoder driver has returned an error
 * for more than ODOM_ENCODER_FAIL_LIMIT consecutive cycles. The main loop
 * uses this to suppress odom frames so the upper computer can fall back to
 * its open-loop integrator instead of trusting a stale pose.
 */
uint8 Odometry_IsValid(void);

#endif
