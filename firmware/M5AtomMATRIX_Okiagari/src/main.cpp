#include <Arduino.h>
#include <M5Atom.h>
#include <SCServo.h>
#include <math.h>

#include "OkiagariPolicy.h"

namespace {

constexpr uint32_t kDefaultServoBaud = 1000000;
constexpr int8_t kDefaultServoRxPin = 32;
constexpr int8_t kDefaultServoTxPin = 26;
constexpr uint32_t kServoBaudRates[] = {
    1000000, 500000, 250000, 128000, 115200, 76800,
    57600,   38400,  19200,  14400,  9600,   4800,
};

constexpr uint8_t kServoCount = 2;
uint8_t kServoIds[kServoCount] = {1, 2};

constexpr uint16_t kServoSpeed = 1200;
constexpr uint8_t kServoAcc = 150;
constexpr uint16_t kServoTorque = 800;

constexpr float kPolicyHz = 50.0f;
constexpr uint32_t kPolicyPeriodMs = static_cast<uint32_t>(1000.0f / kPolicyHz);
constexpr float kPolicyDt = 1.0f / kPolicyHz;

constexpr float kEpisodeLengthS = 4.0f;
constexpr float kDropSettleTimeS = 0.35f;
constexpr float kReferenceEndTimeS = 3.50f;

constexpr float kActionScale1Rad = 1.20f;
constexpr float kActionScale2Rad = 1.50f;
constexpr float kJoint1LimitRad = 1.57f;
constexpr float kJoint2LimitRad = 2.09f;
constexpr float kGyroScale = 0.25f;
constexpr float kJointVelScale = 0.10f;
constexpr float kServoSpeedLimitRadS = 1.0471976f / 0.09f;
constexpr float kAutoStartTiltRad = 0.75f;
constexpr float kImuAccSignX = 1.0f;
constexpr float kImuAccSignY = -1.0f;
constexpr float kImuAccSignZ = -1.0f;
constexpr float kImuGyroSignX = 1.0f;
constexpr float kImuGyroSignY = -1.0f;

constexpr int16_t kServoMinTicks = 0;
constexpr int16_t kServoMaxTicks = 4095;
constexpr int16_t kServoCenterTicks[kServoCount] = {2047, 2047};
constexpr float kServoSign[kServoCount] = {1.0f, 1.0f};
constexpr float kServoTicksPerRad[kServoCount] = {
    4095.0f / (2.0f * PI),
    4095.0f / (2.0f * PI),
};

struct ReferencePoint {
    float t;
    float q1;
    float q2;
};

constexpr ReferencePoint kReferenceRollPos[] = {
    {1.00f, 0.00f, 0.00f},
    {1.50f, -1.57f, 0.00f},
    {3.00f, -1.57f, 0.00f},
    {3.50f, 0.00f, 0.00f},
};

constexpr ReferencePoint kReferenceRollNeg[] = {
    {1.00f, 0.00f, 0.00f},
    {1.50f, 1.57f, 0.00f},
    {3.00f, 1.57f, 0.00f},
    {3.50f, 0.00f, 0.00f},
};

constexpr ReferencePoint kReferencePitchPos[] = {
    {1.00f, 0.00f, 0.00f},
    {1.50f, 0.00f, -2.09f},
    {3.00f, 0.00f, -2.09f},
    {3.50f, 0.00f, 0.00f},
};

constexpr ReferencePoint kReferencePitchNeg[] = {
    {1.00f, 0.00f, 0.00f},
    {1.50f, 0.00f, 2.09f},
    {3.00f, 0.00f, 2.09f},
    {3.50f, 0.00f, 0.00f},
};

enum class RunMode : uint8_t {
    Reference,
    Policy,
};

enum class ReferenceMode : uint8_t {
    Auto,
    RollPos,
    RollNeg,
    PitchPos,
    PitchNeg,
};

HLSCL servoBus;

RunMode runMode = RunMode::Policy;
ReferenceMode selectedReference = ReferenceMode::Auto;
ReferenceMode activeReference = ReferenceMode::RollPos;

uint8_t servoBaudIndex = 0;
uint32_t servoBaud = kDefaultServoBaud;
int8_t servoRxPin = kDefaultServoRxPin;
int8_t servoTxPin = kDefaultServoTxPin;

bool controllerEnabled = false;
bool policyAvailable = false;
bool autoStartOnTilt = true;
bool verboseServoLog = true;
uint32_t nextPolicyMs = 0;
uint32_t episodeStartMs = 0;
uint32_t lastLedMs = 0;
uint32_t lastDebugMs = 0;
uint32_t lastServoWriteDebugMs = 0;
uint32_t lastIdleImuDebugMs = 0;
float lastRollRad = 0.0f;
float lastPitchRad = 0.0f;

float jointPosRad[kServoCount] = {0.0f, 0.0f};
float jointVelRadS[kServoCount] = {0.0f, 0.0f};
float servoTargetRad[kServoCount] = {0.0f, 0.0f};

float clampFloat(float value, float low, float high) {
    if (value < low) return low;
    if (value > high) return high;
    return value;
}

int16_t clampTicks(int32_t ticks) {
    if (ticks < kServoMinTicks) return kServoMinTicks;
    if (ticks > kServoMaxTicks) return kServoMaxTicks;
    return ticks;
}

float ticksToRad(uint8_t index, int ticks) {
    return (static_cast<float>(ticks) - kServoCenterTicks[index]) /
           (kServoSign[index] * kServoTicksPerRad[index]);
}

int16_t radToTicks(uint8_t index, float radians) {
    const float raw = kServoCenterTicks[index] +
                      kServoSign[index] * radians * kServoTicksPerRad[index];
    return clampTicks(lroundf(raw));
}

const char* referenceName(ReferenceMode mode) {
    switch (mode) {
        case ReferenceMode::RollPos:
            return "roll_pos";
        case ReferenceMode::RollNeg:
            return "roll_neg";
        case ReferenceMode::PitchPos:
            return "pitch_pos";
        case ReferenceMode::PitchNeg:
            return "pitch_neg";
        case ReferenceMode::Auto:
        default:
            return "auto";
    }
}

const char* servoErrorName(uint8_t err) {
    switch (err) {
        case 0:
            return "OK";
        case ERR_NO_REPLY:
            return "NO_REPLY";
        case ERR_CRC_CMP:
            return "CRC";
        case ERR_SLAVE_ID:
            return "SLAVE_ID";
        case ERR_BUFF_LEN:
            return "BUFF_LEN";
        default:
            return "UNKNOWN";
    }
}

void printServoResult(const char* op, uint8_t id, int result) {
    const uint8_t err = servoBus.getLastError();
    Serial.printf("[servo] %s id=%u result=%d err=%u(%s) state=%u\n", op, id,
                  result, err, servoErrorName(err), servoBus.getState());
}

void beginServoUart() {
    Serial2.end();
    delay(20);
    Serial2.begin(servoBaud, SERIAL_8N1, servoRxPin, servoTxPin);
    servoBus.pSerial = &Serial2;
    servoBus.IOTimeOut = 30;
    delay(100);

    Serial.printf("[servo] uart begin Serial2 baud=%lu rx=%d tx=%d timeout=%lu\n",
                  static_cast<unsigned long>(servoBaud), servoRxPin,
                  servoTxPin, servoBus.IOTimeOut);
}

void cycleServoBaud() {
    servoBaudIndex =
        (servoBaudIndex + 1) %
        (sizeof(kServoBaudRates) / sizeof(kServoBaudRates[0]));
    servoBaud = kServoBaudRates[servoBaudIndex];
    beginServoUart();
}

void swapServoPins() {
    const int8_t oldRx = servoRxPin;
    servoRxPin = servoTxPin;
    servoTxPin = oldRx;
    beginServoUart();
}

void setStatusColor(const CRGB& color) {
    M5.dis.fillpix(color);
}

void updateStatusLed() {
    const uint32_t now = millis();
    if (now - lastLedMs < 200) return;
    lastLedMs = now;

    if (!controllerEnabled) {
        setStatusColor(CRGB(0, 0, 24));
    } else if (!policyAvailable) {
        setStatusColor(CRGB(24, 16, 0));
    } else {
        setStatusColor(CRGB(0, 24, 0));
    }
}

void writeServoTargets() {
    s16 positions[kServoCount];
    u16 speeds[kServoCount];
    u8 accs[kServoCount];
    u16 torques[kServoCount];

    for (uint8_t i = 0; i < kServoCount; ++i) {
        positions[i] = radToTicks(i, servoTargetRad[i]);
        speeds[i] = kServoSpeed;
        accs[i] = kServoAcc;
        torques[i] = kServoTorque;
    }

    servoBus.SyncWritePosEx(kServoIds, kServoCount, positions, speeds, accs,
                            torques);

    const uint32_t now = millis();
    if (verboseServoLog && now - lastServoWriteDebugMs >= 200) {
        lastServoWriteDebugMs = now;
        Serial.printf(
            "[servo] syncWrite pos=%d,%d target_rad=%.3f,%.3f speed=%u acc=%u torque=%u\n",
            positions[0], positions[1], servoTargetRad[0], servoTargetRad[1],
            kServoSpeed, kServoAcc, kServoTorque);
    }
}

void moveTargetsToward(const float desired[kServoCount]) {
    const float maxDelta = kServoSpeedLimitRadS * kPolicyDt;
    for (uint8_t i = 0; i < kServoCount; ++i) {
        const float delta = clampFloat(desired[i] - servoTargetRad[i],
                                       -maxDelta, maxDelta);
        servoTargetRad[i] += delta;
    }
}

void readServoState() {
    static float prevPosRad[kServoCount] = {0.0f, 0.0f};

    for (uint8_t i = 0; i < kServoCount; ++i) {
        const int posTicks = servoBus.ReadPos(kServoIds[i]);
        if (posTicks >= kServoMinTicks && posTicks <= kServoMaxTicks) {
            jointPosRad[i] = ticksToRad(i, posTicks);
        }

        const int speedTicks = servoBus.ReadSpeed(kServoIds[i]);
        if (speedTicks >= -32768 && speedTicks <= 32767) {
            jointVelRadS[i] = (jointPosRad[i] - prevPosRad[i]) / kPolicyDt;
        } else {
            jointVelRadS[i] = 0.0f;
        }
        prevPosRad[i] = jointPosRad[i];
    }
}

void printServoSnapshot() {
    Serial.println("[servo] snapshot begin");
    for (uint8_t i = 0; i < kServoCount; ++i) {
        const uint8_t id = kServoIds[i];
        const int ping = servoBus.Ping(id);
        const uint8_t pingErr = servoBus.getLastError();
        const int mode = servoBus.readByte(id, HLSCL_MODE);
        const uint8_t modeErr = servoBus.getLastError();
        const int torqueEnable = servoBus.readByte(id, HLSCL_TORQUE_ENABLE);
        const uint8_t torqueErr = servoBus.getLastError();
        const int pos = servoBus.ReadPos(id);
        const uint8_t posErr = servoBus.getLastError();
        const int speed = servoBus.ReadSpeed(id);
        const uint8_t speedErr = servoBus.getLastError();
        const int voltage = servoBus.ReadVoltage(id);
        const uint8_t voltageErr = servoBus.getLastError();
        const int temp = servoBus.ReadTemper(id);
        const uint8_t tempErr = servoBus.getLastError();

        Serial.printf(
            "[servo] id=%u ping=%d(err=%u:%s) mode=%d(err=%u:%s) torque=%d(err=%u:%s) pos=%d(err=%u:%s) speed=%d(err=%u:%s) voltage=%d(err=%u:%s) temp=%d(err=%u:%s)\n",
            id, ping, pingErr, servoErrorName(pingErr), mode, modeErr,
            servoErrorName(modeErr), torqueEnable, torqueErr,
            servoErrorName(torqueErr), pos, posErr, servoErrorName(posErr),
            speed, speedErr, servoErrorName(speedErr), voltage, voltageErr,
            servoErrorName(voltageErr), temp, tempErr, servoErrorName(tempErr));
    }
    Serial.println("[servo] snapshot end");
}

void writeIndividualTargetTicks(int16_t offsetTicks) {
    Serial.printf("[servo] individual WritePosEx offset=%d\n", offsetTicks);
    for (uint8_t i = 0; i < kServoCount; ++i) {
        const int16_t position =
            clampTicks(static_cast<int32_t>(kServoCenterTicks[i]) + offsetTicks);
        servoTargetRad[i] = ticksToRad(i, position);
        const int result = servoBus.WritePosEx(kServoIds[i], position,
                                               kServoSpeed, kServoAcc,
                                               kServoTorque);
        Serial.printf("[servo] write id=%u pos=%d rad=%.3f\n", kServoIds[i],
                      position, servoTargetRad[i]);
        printServoResult("WritePosEx", kServoIds[i], result);
    }
}

void runServoDiagnostics() {
    Serial.printf("[servo] uart=Serial2 baud=%lu rx=%d tx=%d timeout=%lu ids=%u,%u center=%d,%d\n",
                  static_cast<unsigned long>(servoBaud), servoRxPin,
                  servoTxPin, servoBus.IOTimeOut, kServoIds[0], kServoIds[1],
                  kServoCenterTicks[0], kServoCenterTicks[1]);

    for (uint8_t i = 0; i < kServoCount; ++i) {
        const uint8_t id = kServoIds[i];
        printServoResult("Ping", id, servoBus.Ping(id));
        printServoResult("ServoMode", id, servoBus.ServoMode(id));
        printServoResult("EnableTorque", id, servoBus.EnableTorque(id, 1));
    }

    printServoSnapshot();
}

void scanServoIds() {
    Serial.printf("[servo] scan ids 0..10 baud=%lu rx=%d tx=%d\n",
                  static_cast<unsigned long>(servoBaud), servoRxPin,
                  servoTxPin);
    for (uint8_t id = 0; id <= 10; ++id) {
        const int ping = servoBus.Ping(id);
        const uint8_t err = servoBus.getLastError();
        Serial.printf("[servo] scan id=%u ping=%d err=%u(%s)\n", id, ping, err,
                      servoErrorName(err));
        delay(20);
    }
}

void readImuAttitude(float& roll, float& pitch, float& gyroXRadS,
                     float& gyroYRadS) {
    float accX = 0.0f;
    float accY = 0.0f;
    float accZ = 1.0f;
    float gyroXDps = 0.0f;
    float gyroYDps = 0.0f;
    float gyroZDps = 0.0f;

    M5.IMU.getAccelData(&accX, &accY, &accZ);
    M5.IMU.getGyroData(&gyroXDps, &gyroYDps, &gyroZDps);
    (void)gyroZDps;

    accX *= kImuAccSignX;
    accY *= kImuAccSignY;
    accZ *= kImuAccSignZ;
    gyroXDps *= kImuGyroSignX;
    gyroYDps *= kImuGyroSignY;

    pitch = asinf(clampFloat(-accX, -1.0f, 1.0f));
    roll = atan2f(accY, accZ);
    gyroXRadS = gyroXDps * DEG_TO_RAD;
    gyroYRadS = gyroYDps * DEG_TO_RAD;
    lastRollRad = roll;
    lastPitchRad = pitch;
}

ReferenceMode detectReferenceMode() {
    float roll = 0.0f;
    float pitch = 0.0f;
    float gyroXRadS = 0.0f;
    float gyroYRadS = 0.0f;
    readImuAttitude(roll, pitch, gyroXRadS, gyroYRadS);

    if (fabsf(roll) >= fabsf(pitch)) {
        return roll >= 0.0f ? ReferenceMode::RollPos : ReferenceMode::RollNeg;
    }
    return pitch >= 0.0f ? ReferenceMode::PitchPos : ReferenceMode::PitchNeg;
}

float taskTimeSeconds() {
    if (!controllerEnabled) return 0.0f;
    return 0.001f * static_cast<float>(millis() - episodeStartMs);
}

void buildObservation(float obs[OkiagariPolicy::kObservationSize]) {
    float roll = 0.0f;
    float pitch = 0.0f;
    float gyroXRadS = 0.0f;
    float gyroYRadS = 0.0f;
    readImuAttitude(roll, pitch, gyroXRadS, gyroYRadS);

    const float taskTime = max(0.0f, taskTimeSeconds() - kDropSettleTimeS);
    const float taskLength = max(kEpisodeLengthS - kDropSettleTimeS, 1.0e-6f);
    const float episodePhase = clampFloat(taskTime / taskLength, 0.0f, 1.0f);

    // Must match okiagari_getup_env.py::_get_observations().
    obs[0] = sinf(roll);
    obs[1] = cosf(roll);
    obs[2] = sinf(pitch);
    obs[3] = cosf(pitch);
    obs[4] = gyroXRadS * kGyroScale;
    obs[5] = gyroYRadS * kGyroScale;
    obs[6] = clampFloat(jointPosRad[0] / kActionScale1Rad, -1.5f, 1.5f);
    obs[7] = clampFloat(jointPosRad[1] / kActionScale2Rad, -1.5f, 1.5f);
    obs[8] = jointVelRadS[0] * kJointVelScale;
    obs[9] = jointVelRadS[1] * kJointVelScale;
    obs[10] = servoTargetRad[0] / kJoint1LimitRad;
    obs[11] = servoTargetRad[1] / kJoint2LimitRad;
    obs[12] = episodePhase;
}

void referenceTarget(ReferenceMode mode, float taskTime, float target[kServoCount]) {
    const ReferencePoint* ref = kReferenceRollPos;
    size_t count = sizeof(kReferenceRollPos) / sizeof(kReferenceRollPos[0]);

    switch (mode) {
        case ReferenceMode::RollNeg:
            ref = kReferenceRollNeg;
            count = sizeof(kReferenceRollNeg) / sizeof(kReferenceRollNeg[0]);
            break;
        case ReferenceMode::PitchPos:
            ref = kReferencePitchPos;
            count = sizeof(kReferencePitchPos) / sizeof(kReferencePitchPos[0]);
            break;
        case ReferenceMode::PitchNeg:
            ref = kReferencePitchNeg;
            count = sizeof(kReferencePitchNeg) / sizeof(kReferencePitchNeg[0]);
            break;
        case ReferenceMode::RollPos:
        case ReferenceMode::Auto:
        default:
            break;
    }

    target[0] = 0.0f;
    target[1] = 0.0f;

    if (taskTime < ref[0].t) return;

    for (size_t i = 0; i + 1 < count; ++i) {
        if (taskTime >= ref[i].t && taskTime < ref[i + 1].t) {
            const float alpha =
                clampFloat((taskTime - ref[i].t) / (ref[i + 1].t - ref[i].t),
                           0.0f, 1.0f);
            target[0] = ref[i].q1 + (ref[i + 1].q1 - ref[i].q1) * alpha;
            target[1] = ref[i].q2 + (ref[i + 1].q2 - ref[i].q2) * alpha;
            return;
        }
    }

    target[0] = ref[count - 1].q1;
    target[1] = ref[count - 1].q2;
}

void sanitizeAction(float action[OkiagariPolicy::kActionSize]) {
    for (size_t i = 0; i < OkiagariPolicy::kActionSize; ++i) {
        if (!isfinite(action[i])) action[i] = 0.0f;
        action[i] = clampFloat(action[i], -1.0f, 1.0f);
    }
}

void runPolicyStep() {
    readServoState();

    float obs[OkiagariPolicy::kObservationSize];
    float action[OkiagariPolicy::kActionSize] = {0.0f, 0.0f};
    buildObservation(obs);

    float desiredRad[kServoCount] = {0.0f, 0.0f};
    const float elapsed = taskTimeSeconds();
    const float taskTime = max(0.0f, elapsed - kDropSettleTimeS);

    if (runMode == RunMode::Reference) {
        policyAvailable = true;
        if (controllerEnabled && elapsed >= kDropSettleTimeS) {
            referenceTarget(activeReference, taskTime, desiredRad);
        }
    } else {
        policyAvailable = OkiagariPolicy::run(obs, action);
        sanitizeAction(action);
    }

    if (runMode == RunMode::Policy && controllerEnabled && policyAvailable &&
        elapsed >= kDropSettleTimeS) {
        desiredRad[0] = action[0] * kJoint1LimitRad;
        desiredRad[1] = action[1] * kJoint2LimitRad;
    }

    moveTargetsToward(desiredRad);
    writeServoTargets();

    const uint32_t now = millis();
    if (now - lastDebugMs >= 100) {
        lastDebugMs = now;
        Serial.printf(
            "enabled=%d mode=%s ref=%s elapsed=%.3f task=%.3f phase=%.3f roll=%.3f pitch=%.3f obs0=%.3f obs2=%.3f action=%.3f,%.3f desired=%.3f,%.3f target=%.3f,%.3f joint=%.3f,%.3f\n",
            controllerEnabled ? 1 : 0,
            runMode == RunMode::Reference ? "reference" : "policy",
            referenceName(activeReference), elapsed, taskTime, obs[12],
            lastRollRad, lastPitchRad, obs[0], obs[2], action[0], action[1],
            desiredRad[0], desiredRad[1], servoTargetRad[0],
            servoTargetRad[1], jointPosRad[0], jointPosRad[1]);
    }
}

bool referenceFinished() {
    return runMode == RunMode::Reference && controllerEnabled &&
           taskTimeSeconds() - kDropSettleTimeS > kReferenceEndTimeS + 0.1f;
}

void startController() {
    if (runMode == RunMode::Reference) {
        activeReference = selectedReference == ReferenceMode::Auto
                              ? detectReferenceMode()
                              : selectedReference;
    }
    controllerEnabled = true;
    episodeStartMs = millis();
    nextPolicyMs = millis();
    servoTargetRad[0] = 0.0f;
    servoTargetRad[1] = 0.0f;
    Serial.printf("controller enabled, mode=%s, reference=%s\n",
                  runMode == RunMode::Reference ? "reference" : "policy",
                  referenceName(activeReference));
}

void handleIdleTiltTrigger() {
    float roll = 0.0f;
    float pitch = 0.0f;
    float gyroXRadS = 0.0f;
    float gyroYRadS = 0.0f;
    readImuAttitude(roll, pitch, gyroXRadS, gyroYRadS);
    const float tilt = max(fabsf(roll), fabsf(pitch));

    const uint32_t now = millis();
    if (now - lastIdleImuDebugMs >= 500) {
        lastIdleImuDebugMs = now;
        Serial.printf(
            "[imu] idle roll=%.3f pitch=%.3f tilt=%.3f threshold=%.3f auto=%d\n",
            roll, pitch, tilt, kAutoStartTiltRad, autoStartOnTilt ? 1 : 0);
    }

    if (autoStartOnTilt && tilt >= kAutoStartTiltRad) {
        Serial.printf("[imu] tilt trigger roll=%.3f pitch=%.3f tilt=%.3f\n",
                      roll, pitch, tilt);
        startController();
    }
}

void stopController() {
    controllerEnabled = false;
    servoTargetRad[0] = 0.0f;
    servoTargetRad[1] = 0.0f;
    writeServoTargets();
    Serial.println("controller disabled");
}

void handleInputs() {
    while (Serial.available() > 0) {
        const char c = static_cast<char>(Serial.read());
        if (c == 'e' || c == 'E') startController();
        if (c == 'd' || c == 'D') stopController();
        if (c == 'a' || c == 'A') {
            runMode = RunMode::Reference;
            selectedReference = ReferenceMode::Auto;
            Serial.println("reference mode: auto");
        }
        if (c == '1') {
            runMode = RunMode::Reference;
            selectedReference = ReferenceMode::RollPos;
            Serial.println("reference mode: roll_pos");
        }
        if (c == '2') {
            runMode = RunMode::Reference;
            selectedReference = ReferenceMode::RollNeg;
            Serial.println("reference mode: roll_neg");
        }
        if (c == '3') {
            runMode = RunMode::Reference;
            selectedReference = ReferenceMode::PitchPos;
            Serial.println("reference mode: pitch_pos");
        }
        if (c == '4') {
            runMode = RunMode::Reference;
            selectedReference = ReferenceMode::PitchNeg;
            Serial.println("reference mode: pitch_neg");
        }
        if (c == 'p' || c == 'P') {
            runMode = RunMode::Policy;
            Serial.println("policy mode");
        }
        if (c == 'm' || c == 'M') {
            autoStartOnTilt = !autoStartOnTilt;
            Serial.printf("[imu] auto tilt start %s\n",
                          autoStartOnTilt ? "on" : "off");
        }
        if (c == 'i' || c == 'I') {
            runServoDiagnostics();
        }
        if (c == 'g' || c == 'G') {
            printServoSnapshot();
        }
        if (c == 's' || c == 'S') {
            scanServoIds();
        }
        if (c == 'b' || c == 'B') {
            cycleServoBaud();
            runServoDiagnostics();
        }
        if (c == 'x' || c == 'X') {
            swapServoPins();
            runServoDiagnostics();
        }
        if (c == 't' || c == 'T') {
            writeIndividualTargetTicks(200);
        }
        if (c == 'y' || c == 'Y') {
            writeIndividualTargetTicks(-200);
        }
        if (c == 'v' || c == 'V') {
            verboseServoLog = !verboseServoLog;
            Serial.printf("[servo] verbose log %s\n",
                          verboseServoLog ? "on" : "off");
        }
        if (c == 'z' || c == 'Z') {
            servoTargetRad[0] = 0.0f;
            servoTargetRad[1] = 0.0f;
            writeIndividualTargetTicks(0);
            Serial.println("zero target sent");
        }
    }
}

void initServos() {
    Serial.println("[servo] init begin");
    beginServoUart();
    runServoDiagnostics();
    writeServoTargets();
    Serial.println("[servo] init end");
}

}  // namespace

void setup() {
    M5.begin(true, true, true);
    M5.IMU.Init();
    M5.dis.setBrightness(20);

    initServos();
    setStatusColor(CRGB(0, 0, 24));

    Serial.println("Okiagari policy runner ready");
    Serial.println("default: policy. send 'e' enable, 'd' disable, 'z' zero");
    Serial.println("mode select: 'p' policy, 'a' reference auto, '1' roll_pos, '2' roll_neg, '3' pitch_pos, '4' pitch_neg");
    Serial.println("tilt start: auto by default, 'm' toggles auto tilt start");
    Serial.println("servo debug: 'i' diag, 'g' read, 's' scan IDs, 'b' next baud, 'x' swap rx/tx");
    Serial.println("servo move test: 't' +200tick, 'y' -200tick, 'z' center, 'v' verbose toggle");
}

void loop() {
    handleInputs();
    updateStatusLed();

    if (!controllerEnabled) {
        handleIdleTiltTrigger();
        delay(2);
        return;
    }

    const uint32_t now = millis();
    if (static_cast<int32_t>(now - nextPolicyMs) >= 0) {
        nextPolicyMs += kPolicyPeriodMs;
        runPolicyStep();
        if (referenceFinished()) {
            Serial.println("[ref] finished; stopping to allow next tilt re-detect");
            stopController();
        }
    }

    delay(1);
}
