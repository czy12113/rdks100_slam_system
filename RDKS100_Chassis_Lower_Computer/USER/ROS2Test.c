#include "include.h"

/*
 * This file is kept in the Keil project for manual bench tests only.
 * The production firmware uses ROS2Protocol.c and main.c.
 */
#ifndef ENABLE_ROS2_TEST_MODULE
#define ENABLE_ROS2_TEST_MODULE 0
#endif

#if ENABLE_ROS2_TEST_MODULE

#ifdef USE_ROS2_PROTOCOL

static volatile uint8 odom_update_pending = 0;
static volatile uint8 odom_send_pending = 0;

void ROS2_TestTimerCallback(void)
{
    static uint16 timer_count = 0;

    timer_count++;
    ROS2Protocol_1msTick();

    if((timer_count % 10) == 0)
    {
        odom_update_pending = 1;
    }

    if(timer_count >= 50)
    {
        timer_count = 0;
        odom_send_pending = 1;
    }
}

void ROS2_TestTask(void)
{
    int32 pos_x;
    int32 pos_y;
    int16 yaw;
    int16 linear_vel;
    int16 angular_vel;

    if(ROS2Protocol_TakeTimeoutStop())
    {
        AckermannStop();
    }

    if(odom_update_pending)
    {
        odom_update_pending = 0;
        Odometry_Update();
    }

    if(odom_send_pending)
    {
        odom_send_pending = 0;
        Odometry_GetDataROS2(&pos_x, &pos_y, &yaw, &linear_vel, &angular_vel);
        ROS2Protocol_SendOdom(pos_x, pos_y, yaw, linear_vel, angular_vel);
    }
}

#endif

#endif
