#ifndef _ACKERMANN_CONTROL_H_
#define _ACKERMANN_CONTROL_H_

void AckermannInit(void);

void AckermannGoStraight(int8 speed);
void AckermannTurn(int8 speed, uint16 angle);
void AckermannTurnLeft(int8 speed, uint8 turnLevel);
void AckermannTurnRight(int8 speed, uint8 turnLevel);
void AckermannStop(void);
void AckermannSetSteeringAngle(uint16 angle);

/* Call every MOTOR_TASK_PERIOD_MS from the main loop, not from interrupts. */
void AckermannTask(void);

/* Return the latest commanded steering angle in radians. Used by the
 * Ackermann odometry model so it does not need to maintain its own copy of
 * the servo state. Positive = left, negative = right, 0 = centered.
 */
float AckermannGetSteeringAngleRad(void);

void AckermannTestSPath(void);
void AckermannTest8Path(void);
void AckermannTestParking(void);

#endif
