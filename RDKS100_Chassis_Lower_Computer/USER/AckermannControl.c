#include "include.h"

#define SPEED_STOP          0
#define SPEED_SLOW          30
#define SPEED_MEDIUM        50
#define SPEED_FAST          80
#define MOTOR_STOP_IMMEDIATE_REPEATS   MOTOR_STOP_RETRY_COUNT

static int8 targetMotorSpeed = 0;
static int8 currentMotorSpeed = 0;
static int8 lastMotorOutput = 0;
static uint16 lastServoPulse = SERVO_CENTER_ANGLE;
static uint8 motorOutputValid = 0;
static uint8 servoStateValid = 0;

static int8 ClampMotorSpeed(int8 speed)
{
    if(speed > 100)
    {
        return 100;
    }
    if(speed < -100)
    {
        return -100;
    }

    return speed;
}

static uint16 ClampServoPulse(uint16 pulse)
{
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

static uint16 AbsPulseDiff(uint16 a, uint16 b)
{
    return (a > b) ? (a - b) : (b - a);
}

static uint8 AbsSpeedDiff(int8 a, int8 b)
{
    int16 diff;

    diff = (int16)a - (int16)b;
    if(diff < 0)
    {
        diff = -diff;
    }

    return (uint8)diff;
}

static int8 RampToward(int8 current, int8 target)
{
    int16 next;
    int16 step;

    if(current == target)
    {
        return current;
    }

    step = MOTOR_ACCEL_STEP;
    if(target == 0 || ((current > 0) != (target > 0)))
    {
        step = MOTOR_DECEL_STEP;
    }

    if(target > current)
    {
        next = (int16)current + step;
        if(next > target)
        {
            next = target;
        }
    }
    else
    {
        next = (int16)current - step;
        if(next < target)
        {
            next = target;
        }
    }

    return (int8)next;
}

static void ApplyServoTarget(uint16 pulse, uint16 time_ms)
{
    pulse = ClampServoPulse(pulse);

    if(!servoStateValid ||
       AbsPulseDiff(pulse, lastServoPulse) >= SERVO_CMD_DEADBAND_US)
    {
        ServoSetPluseAndTime(0, pulse, time_ms);
        lastServoPulse = pulse;
        servoStateValid = 1;
    }
}

static void ApplyMotorOutput(int8 speed)
{
    uint8 write_failed;

    speed = ClampMotorSpeed(speed);

    if(!motorOutputValid ||
       AbsSpeedDiff(speed, lastMotorOutput) >= MOTOR_MIN_CHANGE)
    {
        if(speed == 0)
        {
            write_failed = I2CMotor_Stop();
        }
        else
        {
            write_failed = I2CMotor_SetSpeed(speed);
        }

        if(write_failed == 0)
        {
            lastMotorOutput = speed;
            motorOutputValid = 1;
        }
        else
        {
            motorOutputValid = 0;
        }
    }
}

static void SetMotorTarget(int8 speed, uint8 immediate)
{
    targetMotorSpeed = ClampMotorSpeed(speed);

#if MOTOR_DIRECT_COMMAND_ENABLE
    if(immediate)
    {
        currentMotorSpeed = targetMotorSpeed;
        ApplyMotorOutput(currentMotorSpeed);
    }
#else
    immediate = immediate;
#endif
}

void AckermannInit(void)
{
    InitServo();
    I2CMotor_Init();

    targetMotorSpeed = 0;
    currentMotorSpeed = 0;
    lastMotorOutput = 0;
    motorOutputValid = 0;
    lastServoPulse = SERVO_CENTER_ANGLE;
    servoStateValid = 0;

    I2CMotor_StopReliable(MOTOR_STOP_IMMEDIATE_REPEATS);
    ApplyServoTarget(SERVO_CENTER_ANGLE, SERVO_INIT_TIME_MS);
    DelayMs(600);
}

void AckermannGoStraight(int8 speed)
{
    SetMotorTarget(speed, 1);
    ApplyServoTarget(SERVO_CENTER_ANGLE, SERVO_CENTER_TIME_MS);
}

void AckermannTurn(int8 speed, uint16 angle)
{
    SetMotorTarget(speed, 1);
    ApplyServoTarget(angle, SERVO_TURN_TIME_MS);
}

void AckermannTurnLeft(int8 speed, uint8 turnLevel)
{
    uint16 angle;

    if(turnLevel > 100)
    {
        turnLevel = 100;
    }

    angle = SERVO_CENTER_ANGLE -
            (SERVO_CENTER_ANGLE - SERVO_LEFT_MAX) * turnLevel / 100;
    AckermannTurn(speed, angle);
}

void AckermannTurnRight(int8 speed, uint8 turnLevel)
{
    uint16 angle;

    if(turnLevel > 100)
    {
        turnLevel = 100;
    }

    angle = SERVO_CENTER_ANGLE +
            (SERVO_RIGHT_MAX - SERVO_CENTER_ANGLE) * turnLevel / 100;
    AckermannTurn(speed, angle);
}

void AckermannStop(void)
{
    SetMotorTarget(0, 0);
    currentMotorSpeed = 0;
    motorOutputValid = 0;
    ApplyMotorOutput(0);
    lastMotorOutput = 0;
    ApplyServoTarget(SERVO_CENTER_ANGLE, SERVO_CENTER_TIME_MS);
}

void AckermannSetSteeringAngle(uint16 angle)
{
    ApplyServoTarget(angle, SERVO_INIT_TIME_MS);
}

/* Map the latest servo pulse back to an equivalent steering angle.
 *   pulse == SERVO_CENTER_ANGLE   -> 0 rad
 *   pulse == SERVO_LEFT_MAX       -> +MAX_STEERING_ANGLE rad (left)
 *   pulse == SERVO_RIGHT_MAX      -> -MAX_STEERING_ANGLE rad (right)
 * Mirrors SteeringAngleToServoPulse() in ROS2Protocol.c so the odometry
 * model sees exactly the angle the chassis is actually steering at.
 */
float AckermannGetSteeringAngleRad(void)
{
    int16 offset;
    float normalized;

    offset = (int16)lastServoPulse - (int16)SERVO_CENTER_ANGLE;

    if(offset >= 0)
    {
        /* Pulse > center == servo turning toward SERVO_LEFT_MAX side, which
         * the firmware treats as positive steering. SERVO_LEFT_MAX < center
         * numerically for some carriers, so use the configured span.
         */
        if(SERVO_LEFT_MAX != SERVO_CENTER_ANGLE)
        {
            normalized = (float)offset /
                         (float)(SERVO_LEFT_MAX - SERVO_CENTER_ANGLE);
        }
        else
        {
            normalized = 0.0f;
        }
    }
    else
    {
        if(SERVO_RIGHT_MAX != SERVO_CENTER_ANGLE)
        {
            normalized = (float)offset /
                         (float)(SERVO_CENTER_ANGLE - SERVO_RIGHT_MAX);
        }
        else
        {
            normalized = 0.0f;
        }
    }

    if(normalized > 1.0f)
    {
        normalized = 1.0f;
    }
    if(normalized < -1.0f)
    {
        normalized = -1.0f;
    }

    return normalized * MAX_STEERING_ANGLE;
}

void AckermannTask(void)
{
    currentMotorSpeed = RampToward(currentMotorSpeed, targetMotorSpeed);
    ApplyMotorOutput(currentMotorSpeed);
}

void AckermannTestSPath(void)
{
    AckermannGoStraight(SPEED_MEDIUM);
    DelayMs(2000);

    AckermannTurnLeft(SPEED_MEDIUM, 60);
    DelayMs(2000);

    AckermannGoStraight(SPEED_MEDIUM);
    DelayMs(1000);

    AckermannTurnRight(SPEED_MEDIUM, 60);
    DelayMs(2000);

    AckermannGoStraight(SPEED_MEDIUM);
    DelayMs(2000);

    AckermannStop();
}

void AckermannTest8Path(void)
{
    uint8 i;

    for(i = 0; i < 40; i++)
    {
        AckermannTurnLeft(SPEED_SLOW, 80);
        DelayMs(100);
    }

    for(i = 0; i < 40; i++)
    {
        AckermannTurnRight(SPEED_SLOW, 80);
        DelayMs(100);
    }

    AckermannStop();
}

void AckermannTestParking(void)
{
    AckermannGoStraight(SPEED_SLOW);
    DelayMs(1500);

    AckermannStop();
    DelayMs(500);

    AckermannTurnRight(-SPEED_SLOW, 100);
    DelayMs(2000);

    AckermannGoStraight(-SPEED_SLOW);
    DelayMs(1000);

    AckermannStop();
}
