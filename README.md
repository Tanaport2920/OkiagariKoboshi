# Okiagari Koboshi Robot: Isaac Lab RL + M5Stack ATOM Matrix Deployment

2自由度サーボを持つ起き上がり小法師型ロボットを、Isaac Lab上でシミュレーション・強化学習し、最終的にM5Stack ATOM Matrixへ制御ポリシーを組み込むための開発メモです。

<img width="426" height="240" alt="Real" src="https://github.com/user-attachments/assets/37ba31c5-4610-44a3-ad65-1112a04a87e7" />

<img width="426" height="240" alt="Simulation" src="https://github.com/user-attachments/assets/bc8d1295-2b47-4e73-8e47-dc103e4759b9" />

---

## 1. 目的

本プロジェクトの目的は、2軸サーボロボットを倒れた姿勢から自律的に起き上がらせることです。

開発方針は以下です。

```text
1. CAD / URDF / USD でロボットモデルを作成
2. Isaac Labで物理シミュレーション
3. 手動reference軌道で起き上がり動作を作成
4. referenceを教師軌道としてpolicyを学習
5. 学習済みActorをM5Stack ATOM Matrixへ組み込み
6. STS3032サーボを実機制御
```

---

## 3. 使用環境

### 3.1 シミュレーション環境

```text
OS:
  Ubuntu 24.04

GPU:
  NVIDIA GPU

NVIDIA Driver:
  Isaac Sim / Isaac Labに対応したNVIDIA Driver

Isaac Sim:
  Isaac Sim 5.1.0

Isaac Lab:
  Isaac Lab 2.3系

作業ディレクトリ:
  /workspace/isaaclab
  /workspace/OkiagariKoboshi_ws
```

### 3.2 実機環境

```text
Controller:
  M5Stack ATOM Matrix

MCU:
  ESP32-PICO-D4

IMU:
  MPU6886

Servo:
  FEETECH STS3032 x2

Development:
  PlatformIO
  Arduino framework
```

---

## 4. ディレクトリ構成

推奨構成は以下です。

```text
/workspace/OkiagariKoboshi_ws/
  assets/
    usd/
      okiagarikoboshi.usd
    urdf/
      okiagarikoboshi.urdf
    meshes/

  source/
    okiagari_koboshi_ext/
      pyproject.toml
      okiagari_koboshi_ext/
        __init__.py
        tasks/
          __init__.py
          direct/
            __init__.py
            okiagari_getup/
              __init__.py
              okiagari_getup_env.py
              agents/
                __init__.py
                rsl_rl_ppo_cfg.py
              references/
                __init__.py
                getup_reference.py

  tools/
    export_policy_to_c.py
```

---

## 5. Isaac Lab環境構築

Docker Composeを使う場合、ホスト側の作業ディレクトリは環境変数で渡します。

```bash
cd /path/to/OkiagariKoboshi_ws

OKIAGARI_WS_HOST=/path/to/OkiagariKoboshi_ws \
docker compose -f docker/compose.isaaclab.yml up
```

### 5.1 Isaac Labディレクトリへ移動

Isaac Labの実行は基本的に以下のディレクトリで行います。

```bash
cd /workspace/isaaclab
```

`isaaclab.sh` は `/workspace/isaaclab` にあります。
`/workspace/OkiagariKoboshi_ws` で以下を実行すると失敗します。

```bash
./isaaclab.sh
```

その場合は、必ず以下のように実行します。

```bash
cd /workspace/isaaclab
./isaaclab.sh ...
```

または絶対パスを使います。

```bash
/workspace/isaaclab/isaaclab.sh ...
```

---

## 6. Isaac Lab拡張パッケージのインストール

自作環境 `okiagari_koboshi_ext` をeditable installします。

```bash
cd /workspace/isaaclab

./isaaclab.sh -p -m pip install -e /workspace/OkiagariKoboshi_ws/source/okiagari_koboshi_ext
```

正常に入ると以下のようになります。

```text
Successfully installed okiagari-koboshi-ext-0.1.0
```

コードを変更した後は、念のため再度実行します。

```bash
cd /workspace/isaaclab

./isaaclab.sh -p -m pip install -e /workspace/OkiagariKoboshi_ws/source/okiagari_koboshi_ext
```

---

## 7. URDF / USD

ロボットのUSDファイルは以下を使用します。

```text
/workspace/OkiagariKoboshi_ws/assets/usd/okiagarikoboshi.usd
```

環境コード内では以下のように指定します。

```python
OKIAGARI_USD = "/workspace/OkiagariKoboshi_ws/assets/usd/okiagarikoboshi.usd"
```

関節名は以下です。

```text
revolute1
revolute2
```

body名は以下です。

```text
root
sts3032_horn_1
sts3032_horn
```

---

## 8. WebRTC表示

### 8.1 ロボット表示確認

WebRTCでIsaac Sim画面を表示する場合は以下を使います。

```bash
cd /workspace/isaaclab

PUBLIC_IP=YOUR_PUBLIC_IP \
LIVESTREAM=2 \
ENABLE_CAMERAS=1 \
./isaaclab.sh -p /workspace/OkiagariKoboshi_ws/isaac/scripts/spawn_robot.py \
  --kit_args "--/app/livestream/publicEndpointAddress=YOUR_PUBLIC_IP --/app/livestream/port=49100"
```

WebRTC Client側では以下へ接続します。

```text
YOUR_PUBLIC_IP
```

---

## 9. 学習中にGUIを映す

学習中にGUIを表示する場合は、`--headless` を付けません。

確認用は `num_envs` を少なくします。

```bash
cd /workspace/isaaclab

PUBLIC_IP=YOUR_PUBLIC_IP \
LIVESTREAM=2 \
ENABLE_CAMERAS=1 \
./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/train.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 16 \
  --max_iterations 500 \
  --kit_args "--/app/livestream/publicEndpointAddress=YOUR_PUBLIC_IP --/app/livestream/port=49100"
```

本学習はheadless推奨です。

```bash
cd /workspace/isaaclab

./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/train.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 512 \
  --headless \
  --max_iterations 1500
```

---

## 10. play.pyでの再生

RSL-RLの `play.py` では `--use_last_checkpoint` は使いません。
`--checkpoint` を指定します。

```bash
cd /workspace/isaaclab

CKPT=$(find logs/rsl_rl/okiagari_getup_v2 -type f -name "model_*.pt" | sort -V | tail -n 1)

PUBLIC_IP=YOUR_PUBLIC_IP \
LIVESTREAM=2 \
ENABLE_CAMERAS=1 \
./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/play.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 16 \
  --checkpoint "$CKPT" \
  --kit_args "--/app/livestream/publicEndpointAddress=YOUR_PUBLIC_IP --/app/livestream/port=49100"
```

---

## 11. 観測設計

実機で取得できる量に合わせます。

```text
obs[0]  = sin(roll)
obs[1]  = cos(roll)
obs[2]  = sin(pitch)
obs[3]  = cos(pitch)

obs[4]  = gyro_x * 0.25
obs[5]  = gyro_y * 0.25

obs[6]  = q1 / q1_limit
obs[7]  = q2 / q2_limit

obs[8]  = dq1 * 0.10
obs[9]  = dq2 * 0.10

obs[10] = target1 / q1_limit
obs[11] = target2 / q2_limit
```

M5側でも同じ順番で `obs[12]` を作成します。

---

## 12. action設計

最初はpolicyが関節の絶対角度を出力する設計で試しましたが、最終的には参考記事に合わせて **差分action方式** にします。

```text
action[0] = revolute1 targetの増減
action[1] = revolute2 targetの増減
```

シミュレーション側・実機側で共通して以下のように扱います。

```cpp
target1 += action[0] * 0.08f;
target2 += action[1] * 0.08f;

target1 = constrain(target1, -1.57f, 1.57f);
target2 = constrain(target2, -2.09f, 2.09f);
```

---

## 13. PPO設定

`rsl_rl_ppo_cfg.py` の基本設定です。

```python
from isaaclab.utils import configclass
from isaaclab_rl.rsl_rl import (
    RslRlOnPolicyRunnerCfg,
    RslRlPpoActorCriticCfg,
    RslRlPpoAlgorithmCfg,
)


@configclass
class OkiagariGetupPPORunnerCfg(RslRlOnPolicyRunnerCfg):
    num_steps_per_env = 32
    max_iterations = 1500
    save_interval = 50
    experiment_name = "okiagari_getup_v2"
    empirical_normalization = False

    policy = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        actor_hidden_dims=[64, 64],
        critic_hidden_dims=[64, 64],
        activation="relu",
    )

    algorithm = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.01,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=3.0e-4,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )
```

---

## 14. Ground摩擦設定

起き上がりでは床との摩擦が重要です。
地面摩擦は高めに設定します。

```python
def _setup_scene(self):
    self.robot = Articulation(self.cfg.robot_cfg)

    ground_cfg = GroundPlaneCfg(
        physics_material=sim_utils.RigidBodyMaterialCfg(
            static_friction=3.0,
            dynamic_friction=2.5,
            restitution=0.0,
            friction_combine_mode="max",
            restitution_combine_mode="min",
        )
    )
    spawn_ground_plane(prim_path="/World/ground", cfg=ground_cfg)

    self.scene.clone_environments(copy_from_source=False)
    if self.device == "cpu":
        self.scene.filter_collisions(global_prim_paths=[])
    self.scene.articulations["robot"] = self.robot

    light_cfg = sim_utils.DomeLightCfg(intensity=3000.0, color=(0.9, 0.9, 0.9))
    light_cfg.func("/World/Light", light_cfg)
```

---

## 15. Reference軌道

PPOでゼロから起き上がりを探索させると難しいため、まずは手動referenceを作成します。

形式は以下です。

```python
(時刻[s], revolute1目標角[rad], revolute2目標角[rad])
```

`getup_reference.py` の例です。

```python
GETUP_REFERENCE = {
    "roll_pos": [
        (0.00,  0.00,  0.00),
        (0.40,  0.50,  0.00),
        (0.90,  1.00,  0.00),
        (1.40,  1.57,  0.00),
        (2.00,  0.00,  0.00),
    ],

    "roll_neg": [
        (0.00,  0.00,  0.00),
        (0.40, -0.50,  0.00),
        (0.90, -1.00,  0.00),
        (1.40, -1.57,  0.00),
        (2.00,  0.00,  0.00),
    ],

    "pitch_pos": [
        (0.00,  0.00,  0.00),
        (0.40,  0.00,  0.70),
        (0.90,  0.00,  1.40),
        (1.40,  0.00,  2.09),
        (2.00,  0.00,  0.00),
    ],

    "pitch_neg": [
        (0.00,  0.00,  0.00),
        (0.40,  0.00, -0.70),
        (0.90,  0.00, -1.40),
        (1.40,  0.00, -2.09),
        (2.00,  0.00,  0.00),
    ],
}
```

現在、以下は起き上がり成功済みです。

```text
roll_pos
roll_neg
pitch_pos
pitch_neg
```

---

## 16. referenceの読み込み

`okiagari_getup_env.py` の先頭に追加します。

```python
from .references.getup_reference import GETUP_REFERENCE
```

configには以下を追加します。

```python
scripted_getup_mode = "roll_pos"
use_scripted_control = True
```

---

## 17. reference target計算

4姿勢のreferenceを自動で選ぶため、以下の関数を用意します。

```python
def _get_reference_target(self):
    t = self.episode_length_buf.float() * self.cfg.sim.dt * self.cfg.decimation
    target = torch.zeros(self.num_envs, 2, device=self.device)

    mode_names = ["roll_pos", "roll_neg", "pitch_pos", "pitch_neg"]

    for mode_id, mode_name in enumerate(mode_names):
        env_mask = self._mode_ids == mode_id
        if not torch.any(env_mask):
            continue

        ref = GETUP_REFERENCE[mode_name]

        for i in range(len(ref) - 1):
            t0, q10, q20 = ref[i]
            t1, q11, q21 = ref[i + 1]

            time_mask = (t >= t0) & (t < t1)
            mask = env_mask & time_mask

            alpha = torch.clamp((t - t0) / (t1 - t0), 0.0, 1.0)

            q1 = q10 + (q11 - q10) * alpha
            q2 = q20 + (q21 - q20) * alpha

            target[:, 0] = torch.where(mask, q1, target[:, 0])
            target[:, 1] = torch.where(mask, q2, target[:, 1])

        t_last, q1_last, q2_last = ref[-1]
        mask = env_mask & (t >= t_last)
        target[:, 0] = torch.where(mask, torch.full_like(t, q1_last), target[:, 0])
        target[:, 1] = torch.where(mask, torch.full_like(t, q2_last), target[:, 1])

    return target
```

---

## 18. scripted制御用_apply_action

reference再生確認時は、policy actionを無視してreferenceを流します。

```python
def _apply_action(self):
    self._ensure_action_buffers()

    if self.cfg.use_scripted_control:
        self._servo_targets.copy_(self._get_reference_target())
    else:
        self._servo_targets[:, 0] += self._actions[:, 0] * 0.08
        self._servo_targets[:, 1] += self._actions[:, 1] * 0.08

        self._servo_targets[:, 0] = torch.clamp(self._servo_targets[:, 0], -1.57, 1.57)
        self._servo_targets[:, 1] = torch.clamp(self._servo_targets[:, 1], -2.09, 2.09)

    self.robot.set_joint_position_target(
        self._servo_targets,
        joint_ids=self._joint_ids,
    )
```

---

## 19. action buffer初期化

以下を環境クラス内に用意します。

```python
def _ensure_action_buffers(self):
    if not hasattr(self, "_actions"):
        self._actions = torch.zeros(self.num_envs, 2, device=self.device)

    if not hasattr(self, "_previous_actions"):
        self._previous_actions = torch.zeros(self.num_envs, 2, device=self.device)

    if not hasattr(self, "_servo_targets"):
        self._servo_targets = torch.zeros(self.num_envs, 2, device=self.device)
```

reset時も初期化します。

```python
self._ensure_action_buffers()
self._actions[env_ids] = 0.0
self._previous_actions[env_ids] = 0.0
self._servo_targets[env_ids] = 0.0
```

---

## 20. reference追従報酬

policyにreferenceを真似させるため、報酬にreference追従項を追加します。

```python
ref_target = self._get_reference_target()
joint_pos_now = self.robot.data.joint_pos[:, self._joint_ids]

ref_error = torch.sum((joint_pos_now - ref_target) ** 2, dim=1)
ref_reward = 8.0 * torch.exp(-3.0 * ref_error)
```

rewardに追加します。

```python
reward = (
    ref_reward
    + height_reward
    + upright_reward
    + success_reward
    + ang_vel_penalty
    + joint_vel_penalty
    + action_penalty
    + action_rate_penalty
)
```

---

## 21. 学習の流れ

### 21.1 reference再生確認

```bash
cd /workspace/isaaclab

PUBLIC_IP=YOUR_PUBLIC_IP \
LIVESTREAM=2 \
ENABLE_CAMERAS=1 \
./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/train.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 4 \
  --max_iterations 50 \
  --kit_args "--/app/livestream/publicEndpointAddress=YOUR_PUBLIC_IP --/app/livestream/port=49100"
```

この段階では `use_scripted_control = True` とします。

### 21.2 PPO学習

reference自動選択が確認できたら、以下にします。

```python
use_scripted_control = False
```

その後、headlessで学習します。

```bash
cd /workspace/isaaclab

./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/train.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 512 \
  --headless \
  --max_iterations 1500
```

---

## 22. デバッグメモ

### 22.1 モータが回らない

サイン波を直接 `_apply_action()` で流して確認しました。
サイン波で関節が動いたため、以下は正常と判断しました。

```text
joint_ids
actuator設定
USD joint drive
set_joint_position_target()
```

問題はpolicyと報酬設計側でした。

### 22.2 upright判定

横で寝ている姿勢でも以下のように `z_z` が高く出ました。

```text
x_z ≈ 0
y_z ≈ 0.626
z_z ≈ 0.780
height ≈ 0.025
```

そのため、`upright` 単独ではなく `height` で報酬をゲートするようにしました。

### 22.3 getup_reference.pyが反映されない

`getup_reference.py` を作っても、`okiagari_getup_env.py` がimportしていなければ反映されません。

```python
from .references.getup_reference import GETUP_REFERENCE
```

を追加します。

### 22.4 scripted_getup_modeがない

以下のエラーが出た場合、

```text
AttributeError: 'OkiagariGetupEnvCfg' object has no attribute 'scripted_getup_mode'
```

configに追加します。

```python
scripted_getup_mode = "roll_pos"
```

### 22.5 _servo_targetsがない

以下のエラーが出た場合、

```text
AttributeError: 'OkiagariGetupEnv' object has no attribute '_servo_targets'
```

`_ensure_action_buffers()` に `_servo_targets` の初期化を追加します。

---

## 23. M5Stack ATOM Matrix側の環境構築

### 23.1 PlatformIO設定

`platformio.ini` は以下です。

```ini
[env:m5stack-atom]
platform = espressif32
board = m5stack-atom
framework = arduino

monitor_speed = 115200
upload_speed = 1500000

build_flags =
    -DCORE_DEBUG_LEVEL=1

lib_deps =
    m5stack/M5Atom
    fastled/FastLED
    ftservo/FTServo
```

---

## 24. M5側の推奨構成

```text
OkiagariM5/
  platformio.ini
  src/
    main.cpp
    imu_estimator.h
    imu_estimator.cpp
    servo_bus.h
    servo_bus.cpp
    reference_getup.h
    policy.h
    policy.cpp
    policy_weights.h
    config.h
```

役割：

```text
main.cpp:
  50Hz制御ループ、状態遷移、ボタン処理

imu_estimator:
  roll, pitch, gyro_x, gyro_y取得

servo_bus:
  STS3032への目標角送信
  STS3032から現在角度・速度読み取り

reference_getup:
  手動reference軌道再生

policy:
  学習済みActor MLPのforward実装

policy_weights:
  checkpointからC配列化した重み

config:
  サーボID、角度制限、周期、ゲイン
```

---

## 25. ATOM MatrixとFEETECHサーボドライバの接続

ATOM MatrixのGroveポートを使用します。

```text
ATOM Matrix HY2.0-4P

Black : GND
Red   : 5V
Yellow: G26
White : G32
```

G26/G32をUART2として使います。

```text
G26 = TX
G32 = RX
```

配線：

```text
ATOM Matrix              FEETECHサーボドライバ基板
------------------------------------------------
GND / Black       -----> GND
G26 / Yellow      -----> RX
G32 / White       <----- TX
```

サーボ電源はATOMから取らないようにします。

```text
ATOM:
  USB 5V給電

STS3032:
  外部電源 5〜7.4V
  GNDはATOMと共通
```

UART初期化：

```cpp
HardwareSerial ServoSerial(2);

constexpr int SERVO_TX_PIN = 26;
constexpr int SERVO_RX_PIN = 32;
constexpr int SERVO_BAUD   = 1000000;

void setup() {
    Serial.begin(115200);
    ServoSerial.begin(SERVO_BAUD, SERIAL_8N1, SERVO_RX_PIN, SERVO_TX_PIN);
}
```

ESP32 Arduinoの `begin()` は以下の順です。

```cpp
begin(baud, config, rxPin, txPin)
```

したがって、今回の場合は以下です。

```cpp
ServoSerial.begin(1000000, SERIAL_8N1, 32, 26);
```

---

## 26. M5側の制御周期

Isaac Lab側のpolicy周期は50Hz想定です。
M5側も20ms周期で動かします。

```cpp
constexpr uint32_t POLICY_PERIOD_US = 20000;
```

基本ループ：

```cpp
void loop() {
    static uint32_t last_us = micros();
    uint32_t now = micros();

    if ((uint32_t)(now - last_us) < POLICY_PERIOD_US) {
        return;
    }
    last_us += POLICY_PERIOD_US;

    // 1. IMU取得
    // 2. サーボ状態取得
    // 3. obs作成
    // 4. policy推論
    // 5. target更新
    // 6. サーボへ送信
}
```

---

## 27. M5側reference再生

最初にpolicyを載せるのではなく、Isaac Labで成功したreference軌道をM5で再生します。

`reference_getup.h` の例です。

```cpp
#pragma once
#include <stdint.h>

enum GetupMode {
    ROLL_POS = 0,
    ROLL_NEG = 1,
    PITCH_POS = 2,
    PITCH_NEG = 3,
};

struct Waypoint {
    float t;
    float q1;
    float q2;
};

static const Waypoint REF_ROLL_POS[] = {
    {0.00f, 0.00f, 0.00f},
    {0.40f, 0.50f, 0.00f},
    {0.90f, 1.00f, 0.00f},
    {1.40f, 1.57f, 0.00f},
    {2.00f, 0.00f, 0.00f},
};

static const Waypoint REF_ROLL_NEG[] = {
    {0.00f, 0.00f, 0.00f},
    {0.40f, -0.50f, 0.00f},
    {0.90f, -1.00f, 0.00f},
    {1.40f, -1.57f, 0.00f},
    {2.00f, 0.00f, 0.00f},
};

static const Waypoint REF_PITCH_POS[] = {
    {0.00f, 0.00f, 0.00f},
    {0.40f, 0.00f, 0.70f},
    {0.90f, 0.00f, 1.40f},
    {1.40f, 0.00f, 2.09f},
    {2.00f, 0.00f, 0.00f},
};

static const Waypoint REF_PITCH_NEG[] = {
    {0.00f, 0.00f, 0.00f},
    {0.40f, 0.00f, -0.70f},
    {0.90f, 0.00f, -1.40f},
    {1.40f, 0.00f, -2.09f},
    {2.00f, 0.00f, 0.00f},
};

inline void interpolateReference(
    const Waypoint* ref,
    int n,
    float t,
    float& q1,
    float& q2
) {
    if (t <= ref[0].t) {
        q1 = ref[0].q1;
        q2 = ref[0].q2;
        return;
    }

    for (int i = 0; i < n - 1; i++) {
        if (t >= ref[i].t && t < ref[i + 1].t) {
            float a = (t - ref[i].t) / (ref[i + 1].t - ref[i].t);
            q1 = ref[i].q1 + (ref[i + 1].q1 - ref[i].q1) * a;
            q2 = ref[i].q2 + (ref[i + 1].q2 - ref[i].q2) * a;
            return;
        }
    }

    q1 = ref[n - 1].q1;
    q2 = ref[n - 1].q2;
}

inline void getReferenceTarget(GetupMode mode, float t, float& q1, float& q2) {
    switch (mode) {
        case ROLL_POS:
            interpolateReference(REF_ROLL_POS, sizeof(REF_ROLL_POS) / sizeof(Waypoint), t, q1, q2);
            break;
        case ROLL_NEG:
            interpolateReference(REF_ROLL_NEG, sizeof(REF_ROLL_NEG) / sizeof(Waypoint), t, q1, q2);
            break;
        case PITCH_POS:
            interpolateReference(REF_PITCH_POS, sizeof(REF_PITCH_POS) / sizeof(Waypoint), t, q1, q2);
            break;
        case PITCH_NEG:
            interpolateReference(REF_PITCH_NEG, sizeof(REF_PITCH_NEG) / sizeof(Waypoint), t, q1, q2);
            break;
    }
}
```

---

## 28. checkpointからM5用policyへ変換

M5にPyTorchを載せるのではなく、Actorの重みをC配列に変換します。

### 28.1 exportスクリプト

`/workspace/OkiagariKoboshi_ws/tools/export_policy_to_c.py` を作成します。

```python
import argparse
from pathlib import Path

import torch


def find_actor_layers(state_dict):
    candidates = []

    for k, v in state_dict.items():
        if not k.endswith(".weight"):
            continue
        if v.ndim != 2:
            continue
        if "critic" in k.lower():
            continue
        if "actor" not in k.lower():
            continue

        out_dim, in_dim = v.shape
        candidates.append((k, in_dim, out_dim))

    expected = [(12, 64), (64, 64), (64, 2)]
    layers = []

    for in_dim, out_dim in expected:
        matched = None
        for k, kin, kout in candidates:
            if kin == in_dim and kout == out_dim:
                matched = k
                break
        if matched is None:
            raise RuntimeError(f"Could not find actor layer {in_dim}->{out_dim}. candidates={candidates}")
        layers.append(matched)

    return layers


def array_to_c(name, tensor):
    flat = tensor.detach().cpu().float().contiguous().view(-1).numpy()
    values = ", ".join(f"{x:.9g}f" for x in flat)
    return f"static const float {name}[{len(flat)}] = {{\n    {values}\n}};\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    ckpt = torch.load(args.checkpoint, map_location="cpu")

    if "model_state_dict" in ckpt:
        sd = ckpt["model_state_dict"]
    elif "state_dict" in ckpt:
        sd = ckpt["state_dict"]
    else:
        sd = ckpt

    w_keys = find_actor_layers(sd)
    b_keys = [k.replace(".weight", ".bias") for k in w_keys]

    for k in b_keys:
        if k not in sd:
            raise RuntimeError(f"Missing bias: {k}")

    out = []
    out.append("#pragma once\n")
    out.append("// Auto-generated from RSL-RL Actor checkpoint\n")
    out.append("#define POLICY_IN_DIM 12\n")
    out.append("#define POLICY_H1_DIM 64\n")
    out.append("#define POLICY_H2_DIM 64\n")
    out.append("#define POLICY_OUT_DIM 2\n\n")

    out.append(array_to_c("W1", sd[w_keys[0]]))
    out.append(array_to_c("B1", sd[b_keys[0]]))
    out.append(array_to_c("W2", sd[w_keys[1]]))
    out.append(array_to_c("B2", sd[b_keys[1]]))
    out.append(array_to_c("W3", sd[w_keys[2]]))
    out.append(array_to_c("B3", sd[b_keys[2]]))

    Path(args.out).write_text("\n".join(out))
    print(f"wrote: {args.out}")


if __name__ == "__main__":
    main()
```

### 28.2 実行

```bash
cd /workspace/isaaclab

CKPT=$(find logs/rsl_rl/okiagari_getup_v2 -type f -name "model_*.pt" | sort -V | tail -n 1)

./isaaclab.sh -p /workspace/OkiagariKoboshi_ws/tools/export_policy_to_c.py \
  --checkpoint "$CKPT" \
  --out /workspace/OkiagariKoboshi_ws/policy_weights.h
```

生成された `policy_weights.h` をPlatformIOプロジェクトにコピーします。

```text
src/policy_weights.h
```

---

## 29. M5側policy推論

`policy.h`

```cpp
#pragma once

void policyForward(const float obs[12], float action[2]);
```

`policy.cpp`

```cpp
#include "policy.h"
#include "policy_weights.h"
#include <math.h>

static inline float relu(float x) {
    return x > 0.0f ? x : 0.0f;
}

static void linear(
    const float* x,
    const float* W,
    const float* b,
    float* y,
    int in_dim,
    int out_dim
) {
    for (int o = 0; o < out_dim; o++) {
        float sum = b[o];
        for (int i = 0; i < in_dim; i++) {
            sum += W[o * in_dim + i] * x[i];
        }
        y[o] = sum;
    }
}

void policyForward(const float obs[12], float action[2]) {
    float h1[64];
    float h2[64];
    float out[2];

    linear(obs, W1, B1, h1, 12, 64);
    for (int i = 0; i < 64; i++) {
        h1[i] = relu(h1[i]);
    }

    linear(h1, W2, B2, h2, 64, 64);
    for (int i = 0; i < 64; i++) {
        h2[i] = relu(h2[i]);
    }

    linear(h2, W3, B3, out, 64, 2);

    action[0] = fmaxf(-1.0f, fminf(1.0f, out[0]));
    action[1] = fmaxf(-1.0f, fminf(1.0f, out[1]));
}
```

---

## 30. 実機側obs作成

```cpp
void buildObservation(
    float roll,
    float pitch,
    float gyro_x,
    float gyro_y,
    float q1,
    float q2,
    float dq1,
    float dq2,
    float target1,
    float target2,
    float obs[12]
) {
    obs[0]  = sinf(roll);
    obs[1]  = cosf(roll);
    obs[2]  = sinf(pitch);
    obs[3]  = cosf(pitch);

    obs[4]  = gyro_x * 0.25f;
    obs[5]  = gyro_y * 0.25f;

    obs[6]  = q1 / 1.57f;
    obs[7]  = q2 / 2.09f;

    obs[8]  = dq1 * 0.10f;
    obs[9]  = dq2 * 0.10f;

    obs[10] = target1 / 1.57f;
    obs[11] = target2 / 2.09f;
}
```

---

## 31. 実機投入時の安全制限

最初からpolicyを全力で使わないようにします。

```cpp
action[0] = clampf(action[0], -0.3f, 0.3f);
action[1] = clampf(action[1], -0.3f, 0.3f);
```

段階的に制限を緩めます。

```text
±0.3
↓
±0.5
↓
±0.8
↓
±1.0
```

---

## 32. 実機移植の確認順序

```text
1. ATOM MatrixでLED点灯
2. IMUからroll / pitch / gyro取得
3. STS3032 2個のID確認
4. STS3032へ目標角送信
5. STS3032から現在角度読み取り
6. M5からreference軌道再生
7. 実機で4姿勢から起き上がるか確認
8. policy_weights.hを組み込む
9. policyForwardの出力確認
10. action制限付きでpolicy制御
11. action制限を段階的に緩める
```

---

## 33. 重要方針

以下の順番を守ります。

```text
手動referenceでシミュレーションが立つ
↓
手動referenceで実機が立つ
↓
policyがシミュレーションで立つ
↓
policyをM5へ移植
↓
実機でaction制限付きpolicy確認
↓
制限を緩めて本番動作
```

いきなりpolicyを実機に載せるのではなく、まずM5上でreference再生を成功させます。
これにより、IMU軸、サーボ符号、角度スケール、通信周期のズレを先に潰せます。

---

## 34. よく使うコマンドまとめ

### 拡張パッケージ再インストール

```bash
cd /workspace/isaaclab

./isaaclab.sh -p -m pip install -e /workspace/OkiagariKoboshi_ws/source/okiagari_koboshi_ext
```

### GUIあり学習

```bash
cd /workspace/isaaclab

PUBLIC_IP=YOUR_PUBLIC_IP \
LIVESTREAM=2 \
ENABLE_CAMERAS=1 \
./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/train.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 16 \
  --max_iterations 500 \
  --kit_args "--/app/livestream/publicEndpointAddress=YOUR_PUBLIC_IP --/app/livestream/port=49100"
```

### headless本学習

```bash
cd /workspace/isaaclab

./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/train.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 512 \
  --headless \
  --max_iterations 1500
```

### play

```bash
cd /workspace/isaaclab

CKPT=$(find logs/rsl_rl/okiagari_getup_v2 -type f -name "model_*.pt" | sort -V | tail -n 1)

PUBLIC_IP=YOUR_PUBLIC_IP \
LIVESTREAM=2 \
ENABLE_CAMERAS=1 \
./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/play.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 16 \
  --checkpoint "$CKPT" \
  --kit_args "--/app/livestream/publicEndpointAddress=YOUR_PUBLIC_IP --/app/livestream/port=49100"
```

### policy_weights.h生成

```bash
cd /workspace/isaaclab

CKPT=$(find logs/rsl_rl/okiagari_getup_v2 -type f -name "model_*.pt" | sort -V | tail -n 1)

./isaaclab.sh -p /workspace/OkiagariKoboshi_ws/tools/export_policy_to_c.py \
  --checkpoint "$CKPT" \
  --out /workspace/OkiagariKoboshi_ws/policy_weights.h
```

---

## 35. 現在の実装との差分・補足メモ

このREADMEには開発途中の古い方針も残っています。
現在の `okiagari_getup_env.py` / M5 firmware に合わせる場合は、この章の内容を優先します。

### 35.1 GUIで学習中ロボットが見えない場合

学習中にGUIは表示されていても、カメラが学習中のenvを見ていないことがあります。
512環境で学習すると、ロボットは `env_spacing=2.0` で広い範囲に並びます。

確認時はまずenv数を減らします。

```bash
cd /workspace/isaaclab

PUBLIC_IP=YOUR_PUBLIC_IP \
LIVESTREAM=2 \
ENABLE_CAMERAS=1 \
./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/train.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 1 \
  --max_iterations 1000 \
  --kit_args "--/app/livestream/publicEndpointAddress=YOUR_PUBLIC_IP --/app/livestream/port=49100"
```

多数envで見る場合は、Stage上で以下を選んで `F` キーでフォーカスします。

```text
/World/envs/env_0/Robot
```

### 35.2 現在の観測は13次元

古い記述では12次元になっていますが、現在はphaseを追加して13次元です。

```text
obs[0]  = sin(roll)
obs[1]  = cos(roll)
obs[2]  = sin(pitch)
obs[3]  = cos(pitch)
obs[4]  = gyro_x * 0.25
obs[5]  = gyro_y * 0.25
obs[6]  = clamp(q1 / 1.20, -1.5, 1.5)
obs[7]  = clamp(q2 / 1.50, -1.5, 1.5)
obs[8]  = dq1 * 0.10
obs[9]  = dq2 * 0.10
obs[10] = current_servo_target1 / 1.57
obs[11] = current_servo_target2 / 2.09
obs[12] = episode_phase
```

M5側も `OkiagariPolicy::kObservationSize = 13` です。
12次元で学習したcheckpointは、13次元環境にはそのまま読み込めません。

```text
size mismatch for actor.0.weight:
copying a param with shape torch.Size([64, 12])
the shape in current model is torch.Size([64, 13])
```

この場合は新しい13次元設定で学習し直します。

### 35.3 現在のactionは差分ではなく絶対サーボ目標

古い方針では差分actionでしたが、現在のpolicy actionは絶対目標角です。

```text
action[0] in [-1, 1] -> revolute1 target = action[0] * 1.57 rad
action[1] in [-1, 1] -> revolute2 target = action[1] * 2.09 rad
```

その後、実サーボ仕様に合わせて目標値へ速度制限付きで近づけます。

```text
STS3032想定:
  60度 / 0.09秒

servo_speed_limit:
  1.0471976 rad / 0.09 s
```

Isaac Lab側は200Hz physicsなので、1 physics stepあたり約0.058 radまでしか目標を動かしません。
M5 firmware側も同じ考えで `moveTargetsToward()` により目標角を制限します。

### 35.4 落下してから制御を開始する

現在は、reset直後にpolicy/referenceが動き始めないようにしています。

```python
drop_settle_time_s = 0.35
```

この時間中は以下の動作になります。

```text
servo target        = [0, 0]
reference time      = 0
episode phase       = 0
upright/success報酬 = 無効
```

debug logでは以下で確認します。

```text
active=False  -> 落下・接地待ち
active=True   -> getup制御開始
```

### 35.5 reset姿勢とPOS/NEGの符号

reset時は4種類のreference basinをランダムに選びます。

```text
0: roll_pos
1: roll_neg
2: pitch_pos
3: pitch_neg
```

現在のreset符号は、手動referenceで成功確認した向きに合わせています。

```python
roll[mode_ids == 0] = -0.5 * math.pi  # roll_pos
roll[mode_ids == 1] =  0.5 * math.pi  # roll_neg
pitch[mode_ids == 2] = -0.5 * math.pi # pitch_pos
pitch[mode_ids == 3] =  0.5 * math.pi # pitch_neg
```

さらに、実機での落下ばらつきを想定して高さ、roll、pitch、yaw、初期関節角をランダム化しています。

### 35.6 success判定は直立だけではなく関節ニュートラルも見る

一時期、以下のようなログが出ていました。

```text
z_z=0.962
success=True
joint_pos=[-1.567, -0.040]
```

これは「本体は立っているが、1軸目が限界まで曲がったまま」でも成功になっていた状態です。
現在は、直立だけではsuccessにしません。

現在のsuccess条件は概念的には以下です。

```text
upright_score > 0.95
and joint_pos がニュートラル近傍
and desired target がニュートラル近傍
and active=True
```

debug logには以下も出します。

```text
stand_joint_err
stand_cmd_err
```

ここが大きい場合は「立っているがモータが伸びていない」状態です。

### 35.7 報酬設計の現在の注意点

root heightはsuccess判定に使いません。
このUSDでは、見た目上の直立時でもroot heightが低く出ることがあるためです。

主に使う信号は以下です。

```text
body local Z axisのworld Z成分:
  z_z ≈ 1.0 -> 直立
  z_z ≈ 0.0 -> 横倒し
```

`height_score` はdebug用に残していますが、success判定には使いません。

reference追従報酬は、ゼロ姿勢に止まるだけで得をしないように、現在は「完全一致で0、外れると負」の形にしています。

```text
reference_reward <= 0
command_reference_reward <= 0
```

### 35.8 checkpoint / play.pyの注意

観測次元、ネットワーク構造、action設計を変えた後は、古いcheckpointをそのまま使えません。

特に以下を変更したら新規学習を推奨します。

```text
observation_space
actionの意味
報酬設計
success条件
reference時刻
drop_settle_time_s
```

`play.py` では `--checkpoint` を明示します。

```bash
cd /workspace/isaaclab

CKPT=$(find logs/rsl_rl/okiagari_getup_v2 -type f -name "model_*.pt" | sort -V | tail -n 1)

PUBLIC_IP=YOUR_PUBLIC_IP \
LIVESTREAM=2 \
ENABLE_CAMERAS=1 \
./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/play.py \
  --task OkiagariKoboshi-Getup-Direct-v0 \
  --num_envs 1 \
  --checkpoint "$CKPT" \
  --kit_args "--/app/livestream/publicEndpointAddress=YOUR_PUBLIC_IP --/app/livestream/port=49100"
```

### 35.9 現在のpolicy export

`tools/export_policy_to_c.py` は現在、デフォルトで13次元入力を出力します。

```bash
cd /workspace/isaaclab

CKPT=$(find logs/rsl_rl/okiagari_getup_v2 -type f -name "model_*.pt" | sort -V | tail -n 1)

./isaaclab.sh -p /workspace/OkiagariKoboshi_ws/tools/export_policy_to_c.py \
  --checkpoint "$CKPT" \
  --out /workspace/OkiagariKoboshi_ws/firmware/M5AtomMATRIX_Okiagari/src/policy_weights.h
```

明示する場合は以下です。

```bash
./isaaclab.sh -p /workspace/OkiagariKoboshi_ws/tools/export_policy_to_c.py \
  --checkpoint "$CKPT" \
  --out /workspace/OkiagariKoboshi_ws/firmware/M5AtomMATRIX_Okiagari/src/policy_weights.h \
  --input-dim 13 \
  --h1-dim 64 \
  --h2-dim 64 \
  --output-dim 2
```

M5側は起動時に以下のようなログを出します。

```text
[policy] weights found input=13 h1=64 h2=64 output=2 firmware_obs=13
```

次元が合わない場合は、policy出力を使わずゼロactionへ戻します。

### 35.10 M5 firmware側の現在の対応

M5側も現在のIsaac Lab環境に合わせています。

```text
policy周期:
  50Hz

episode length:
  4.0s

drop settle:
  0.35s

policy action:
  normalized absolute servo target

servo target:
  speed limited
```

`main.cpp` では、policy/referenceともに `kDropSettleTimeS` 経過までは目標角をゼロに保ちます。

```text
elapsed < kDropSettleTimeS:
  desiredRad = [0, 0]

elapsed >= kDropSettleTimeS:
  reference or policy targetを使用
```

実機投入時は、まずReference modeで4姿勢を確認してからPolicy modeへ進みます。
