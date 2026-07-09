# OkiagariKoboshi_ws 環境構築メモ

## 目的

2軸サーボで倒れた状態から起き上がるロボットを、Isaac Sim / Isaac Lab を用いた強化学習で開発する。

全体構成は以下の通り。

```text
PC / GPUサーバ
  Ubuntu 22.04 or 24.04
  NVIDIA Driver
  Docker
  NVIDIA Container Toolkit
  Isaac Sim + Isaac Lab
        ↓
  強化学習 PPO
        ↓
  学習済みpolicyを軽量化
        ↓
M5Stack Core2
  IMUでroll/pitch推定
  policy推論
  2軸サーボへ目標角送信
```

---

## 基本方針

`OkiagariKoboshi_ws` をGitHubで管理する。

ただし、GitHubに入れるのは **Dockerコンテナ本体ではなく、コンテナを再現するための設定ファイル** とする。

GitHubに入れるもの：

```text
Dockerfile
docker-compose.yml
Pythonコード
Isaac Labのtask定義
CADデータ
URDF / USD / mesh
M5Stack Core2のfirmware
policy export用スクリプト
小さい学習済みpolicy
```

GitHubに入れないもの：

```text
Docker image本体
Docker container本体
*.tar のDocker image
Isaac Simのcache
大量の学習ログ
巨大checkpoint
```

---

## 推奨ディレクトリ構成

```text
OkiagariKoboshi_ws/
├── README.md
├── .gitignore
├── .gitattributes
│
├── docker/
│   ├── compose.isaaclab.yml
│   ├── Dockerfile.dev
│   └── .env.example
│
├── cad/
│   ├── original/
│   ├── export_step/
│   ├── export_stl/
│   └── export_urdf/
│
├── assets/
│   ├── urdf/
│   ├── usd/
│   ├── meshes/
│   └── textures/
│
├── isaac/
│   ├── tasks/
│   │   └── okiagari_koboshi/
│   ├── robots/
│   ├── scripts/
│   │   ├── train.py
│   │   ├── play.py
│   │   └── export_policy.py
│   └── configs/
│
├── firmware/
│   └── m5stack_core2/
│       ├── platformio.ini
│       └── src/
│           └── main.cpp
│
├── policies/
│   ├── exported/
│   └── README.md
│
└── docs/
    ├── setup_windows.md
    ├── setup_server.md
    └── sim2real_notes.md
```

---

## Windows側の前提

Windowsでは以下を使う。

```text
Windows
  Docker Desktop
  WSL2
  Ubuntu-24.04 WSL
  VS Code
```

最初にPowerShellでWSLの状態を確認した。

```powershell
wsl -l -v
```

表示が以下のようになっていた。

```text
NAME              STATE           VERSION
docker-desktop    Running         2
```

この状態では、通常作業用のUbuntu WSLがまだ入っていない。
`docker-desktop` はDocker Desktop内部用のWSL環境であり、開発作業に使う場所ではない。

---

## Ubuntu 24.04 WSLの追加

PowerShellで実行する。

```powershell
wsl --install -d Ubuntu-24.04
```

インストール後、確認する。

```powershell
wsl -l -v
```

理想的には以下のようになる。

```text
NAME              STATE           VERSION
Ubuntu-24.04      Running         2
docker-desktop    Running         2
```

Ubuntuに入る。

```powershell
wsl -d Ubuntu-24.04
```

---

## Docker Desktop側の設定

Docker Desktopを開き、Ubuntu WSLとの連携をONにする。

```text
Docker Desktop
  Settings
    Resources
      WSL Integration
        Ubuntu-24.04 をON
```

その後、Ubuntu WSL側でDockerが使えるか確認する。

```bash
docker version
docker ps
```

`docker ps` が通れば、WSLからDocker Desktopを操作できている。

---

## Windows側にあるワークスペースをWSL側へ移動

もともとのプロジェクトはWindows側にある。

```text
C:\Users\hanaj\OkiagariKoboshi_ws
```

WSLからは以下のように見える。

```bash
/mnt/c/Users/hanaj/OkiagariKoboshi_ws
```

ただし、Docker / Isaac Labの開発では、WSLのLinuxファイルシステム側に置く方が安全。

Ubuntu WSLで以下を実行する。

```bash
cd ~
cp -r /mnt/c/Users/hanaj/OkiagariKoboshi_ws ~/OkiagariKoboshi_ws
cd ~/OkiagariKoboshi_ws
```

確認する。

```bash
pwd
ls
```

以下のような場所になっていればよい。

```text
/home/<ユーザー名>/OkiagariKoboshi_ws
```

---

## WindowsエクスプローラからWSL側を見る方法

Windowsのエクスプローラで以下を開く。

```text
\\wsl$\Ubuntu-24.04\home\<ユーザー名>\OkiagariKoboshi_ws
```

以後は、基本的にこのWSL側の `OkiagariKoboshi_ws` を開発対象にする。

---

## VS Codeで開く場所

VS Codeは **コンテナの中ではなく、Ubuntu WSL側で開く**。

正しい流れ：

```bash
cd ~/OkiagariKoboshi_ws
code .
```

VS Code左下に以下のように表示されていればOK。

```text
WSL: Ubuntu-24.04
```

---

## `code .` が使えない場合

コンテナ内で以下を実行しても失敗する。

```bash
code .
```

エラー例：

```text
bash: code: command not found
```

これは正常。
今いる場所がDockerコンテナ内だからである。

例：

```text
root@docker-desktop:/workspace/OkiagariKoboshi_ws#
```

この状態ではVS Codeを起動する場所ではない。

一度コンテナから出る。

```bash
exit
```

その後、Ubuntu WSL側で実行する。

```bash
cd ~/OkiagariKoboshi_ws
code .
```

---

## Docker composeファイル

`docker/compose.isaaclab.yml` を作成する。

```yaml
services:
  isaaclab:
    image: nvcr.io/nvidia/isaac-lab:2.3.2
    container_name: okiagari_isaaclab
    gpus: all
    stdin_open: true
    tty: true

    environment:
      - ACCEPT_EULA=Y
      - PRIVACY_CONSENT=Y
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=all

    volumes:
      - /home/<ユーザー名>/OkiagariKoboshi_ws:/workspace/OkiagariKoboshi_ws:rw
      - /home/<ユーザー名>/OkiagariKoboshi_ws/docker/isaac-cache/kit:/isaac-sim/kit/cache:rw
      - /home/<ユーザー名>/OkiagariKoboshi_ws/docker/isaac-cache/ov:/root/.cache/ov:rw
      - /home/<ユーザー名>/OkiagariKoboshi_ws/docker/isaac-cache/pip:/root/.cache/pip:rw
      - /home/<ユーザー名>/OkiagariKoboshi_ws/docker/isaac-cache/glcache:/root/.cache/nvidia/GLCache:rw
      - /home/<ユーザー名>/OkiagariKoboshi_ws/docker/isaac-cache/computecache:/root/.nv/ComputeCache:rw

    working_dir: /workspace/OkiagariKoboshi_ws

    entrypoint: /bin/bash
    command: -lc "sleep infinity"
```

`/home/<ユーザー名>/OkiagariKoboshi_ws` は、実際の `pwd` の結果に合わせて変更する。

確認方法：

```bash
cd ~/OkiagariKoboshi_ws
pwd
```

例：

```text
/home/hanaj/OkiagariKoboshi_ws
```

その場合は、compose内のパスも以下のようにする。

```yaml
- /home/hanaj/OkiagariKoboshi_ws:/workspace/OkiagariKoboshi_ws:rw
```

---

## 相対パスではなく絶対パスを使う理由

最初は以下のようにしていた。

```yaml
volumes:
  - ..:/workspace/OkiagariKoboshi_ws:rw
```

しかし、この場合、`docker compose` をどの場所から実行したかによって `..` の解釈がずれる可能性がある。

その結果、コンテナ内で作ったファイルがWSL側で見えないことがある。

そのため、確実にするために絶対パスを使う。

```yaml
volumes:
  - /home/<ユーザー名>/OkiagariKoboshi_ws:/workspace/OkiagariKoboshi_ws:rw
```

---

## Isaac Labコンテナの起動

Ubuntu WSL側で実行する。

```bash
cd ~/OkiagariKoboshi_ws
docker compose --project-directory . -f docker/compose.isaaclab.yml pull
```

起動する。

```bash
docker compose --project-directory . -f docker/compose.isaaclab.yml up -d
```

起動確認。

```bash
docker ps
```

`okiagari_isaaclab` が表示されればOK。

---

## コンテナに入る

Ubuntu WSL側で実行する。

```bash
cd ~/OkiagariKoboshi_ws
docker compose --project-directory . -f docker/compose.isaaclab.yml exec isaaclab bash
```

コンテナ内で確認する。

```bash
pwd
ls
```

以下の場所にいればOK。

```text
/workspace/OkiagariKoboshi_ws
```

---

## WSL側とコンテナ側の対応関係

重要な対応関係は以下。

```text
WSL側:
~/OkiagariKoboshi_ws

コンテナ側:
/workspace/OkiagariKoboshi_ws
```

この2つは同じ中身であるべき。

VS Codeで編集する場所：

```text
~/OkiagariKoboshi_ws
```

Isaac Labコンテナ内で実行する場所：

```text
/workspace/OkiagariKoboshi_ws
```

---

## マウント確認テスト

コンテナ内で以下を実行する。

```bash
cd /workspace/OkiagariKoboshi_ws
touch test_from_container.txt
mkdir -p isaac/scripts
touch isaac/scripts/test.txt
```

コンテナから出る。

```bash
exit
```

WSL側で確認する。

```bash
cd ~/OkiagariKoboshi_ws
ls
ls isaac/scripts
```

以下が見えれば成功。

```text
test_from_container.txt
test.txt
```

---

## コンテナ内で作ったフォルダがWSL側に見えない場合

原因はほぼ以下。

```text
コンテナ内の /workspace/OkiagariKoboshi_ws
と
WSL側の ~/OkiagariKoboshi_ws
が同じ場所にマウントされていない
```

対策：

1. `docker/compose.isaaclab.yml` の `volumes:` を絶対パスにする
2. 既存コンテナを作り直す

作り直しコマンド：

```bash
cd ~/OkiagariKoboshi_ws

docker compose --project-directory . -f docker/compose.isaaclab.yml down
docker compose --project-directory . -f docker/compose.isaaclab.yml up -d --force-recreate
```

入り直す。

```bash
docker compose --project-directory . -f docker/compose.isaaclab.yml exec isaaclab bash
```

---

## Isaac Labの存在確認

コンテナ内で実行する。

```bash
ls /workspace
ls /workspace/IsaacLab
```

Isaac LabのPython環境確認。

```bash
cd /workspace/IsaacLab
./isaaclab.sh -p -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

`True` が出れば、PyTorchからGPUが見えている。

---

## 自作スクリプトの実行テスト

コンテナ内で作成する。

```bash
cd /workspace/OkiagariKoboshi_ws
mkdir -p isaac/scripts
nano isaac/scripts/check_env.py
```

中身：

```python
import torch

print("Torch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

print("OkiagariKoboshi workspace OK")
```

実行する。

```bash
cd /workspace/IsaacLab
./isaaclab.sh -p /workspace/OkiagariKoboshi_ws/isaac/scripts/check_env.py
```

これが通れば、自分のGit管理フォルダ内のPythonコードをIsaac Lab環境で実行できている。

---

## Git管理

WSL側でGit管理する。

```bash
cd ~/OkiagariKoboshi_ws
git status
git add .
git commit -m "Add Isaac Lab docker workspace"
```

GitHubリポジトリを作った後、remoteを設定する。

SSHの場合：

```bash
git remote add origin git@github.com:Tanaport2920/OkiagariKoboshi_ws.git
git branch -M main
git push -u origin main
```

HTTPSの場合：

```bash
git remote add origin https://github.com/Tanaport2920/OkiagariKoboshi_ws.git
git branch -M main
git push -u origin main
```

---

## `.gitignore` の例

```gitignore
# Python
__pycache__/
*.pyc
.venv/
venv/

# Docker / large images
*.tar
*.tar.gz
*.img

# Isaac Sim / Isaac Lab caches and logs
docker/isaac-cache/
logs/
runs/
wandb/
.cache/
*.log

# Training artifacts
checkpoints/
*.ckpt
*.pth
*.pt
*.onnx
*.engine

# Allow small exported policy files only if needed
!policies/exported/

# OS
.DS_Store
Thumbs.db

# VSCode
.vscode/
```

---

## CADファイル用 `.gitattributes`

CADやmeshは大きくなりやすいため、Git LFSを使うのが望ましい。

`.gitattributes` の例：

```gitattributes
*.step filter=lfs diff=lfs merge=lfs -text
*.stp  filter=lfs diff=lfs merge=lfs -text
*.stl  filter=lfs diff=lfs merge=lfs -text
*.iges filter=lfs diff=lfs merge=lfs -text
*.igs  filter=lfs diff=lfs merge=lfs -text
*.f3d  filter=lfs diff=lfs merge=lfs -text
*.sldprt filter=lfs diff=lfs merge=lfs -text
*.sldasm filter=lfs diff=lfs merge=lfs -text
*.usd  filter=lfs diff=lfs merge=lfs -text
*.usda filter=lfs diff=lfs merge=lfs -text
*.usdc filter=lfs diff=lfs merge=lfs -text
```

Git LFSを使う場合は一度だけ実行する。

```bash
git lfs install
```

---

## 日常的な開発手順

### 1. VS Codeで編集

Ubuntu WSL側で実行する。

```bash
cd ~/OkiagariKoboshi_ws
code .
```

---

### 2. Isaac Labコンテナを起動

```bash
cd ~/OkiagariKoboshi_ws
docker compose --project-directory . -f docker/compose.isaaclab.yml up -d
```

---

### 3. コンテナに入る

```bash
docker compose --project-directory . -f docker/compose.isaaclab.yml exec isaaclab bash
```

---

### 4. コンテナ内で実行

```bash
cd /workspace/IsaacLab
./isaaclab.sh -p /workspace/OkiagariKoboshi_ws/isaac/scripts/check_env.py
```

---

### 5. コンテナから出る

```bash
exit
```

---

### 6. コンテナを止める

WSL側で実行する。

```bash
cd ~/OkiagariKoboshi_ws
docker compose --project-directory . -f docker/compose.isaaclab.yml down
```

---

## 開発の分担

Windows側では以下を行う。

```text
GitHub管理
VS Codeでコード編集
CAD整理
URDF / USD / mesh整理
M5Stack firmware作成
Isaac Lab用スクリプト作成
軽い動作確認
```

研究室Ubuntu / GPUサーバ側では以下を行う。

```text
NVIDIA Driver
Docker
NVIDIA Container Toolkit
Isaac Sim / Isaac Lab
PPO学習
大量並列シミュレーション
policy export
```

---

## policyの流れ

PC / GPUサーバ側：

```text
Isaac Lab
  ↓
PPO学習
  ↓
PyTorch policy
  ↓
小さいMLPへexport
  ↓
ONNX / C配列 / 手書き推論コード
```

M5Stack Core2側：

```text
IMU取得
  ↓
roll / pitch推定
  ↓
正規化 observation 作成
  ↓
policy推論
  ↓
目標サーボ角度
  ↓
2軸サーボへ送信
```

M5Stack Core2ではPyTorchを動かさない。
小さいMLPをC++で手書き推論する方針がよい。

例：

```text
入力:
  roll
  pitch
  roll_rate
  pitch_rate
  servo1_angle
  servo2_angle

出力:
  servo1_target
  servo2_target
```

小さいpolicy例：

```text
6入力
↓
Linear 16 + tanh
↓
Linear 16 + tanh
↓
Linear 2
```

---

## 現時点での到達状態

現時点でやったこと：

```text
OkiagariKoboshi_ws を作成
CADファイル用フォルダあり
Isaac Lab用 compose ファイルを配置
Docker Desktopで Ubuntu-24.04 WSL Integration をON
Isaac Labコンテナに入れる状態
コンテナ内で code . は使わないことを確認
WSL側とコンテナ側のマウント確認が必要
```

---

## 次にやること

1. `compose.isaaclab.yml` の `volumes:` を絶対パスに修正する
2. コンテナを `down` → `up -d --force-recreate` で作り直す
3. コンテナ内で作ったファイルがWSL側で見えるか確認する
4. VS CodeをWSL側で開く
5. `isaac/scripts/check_env.py` を作成する
6. Isaac LabのPython環境から実行する
7. GitHubにpushする

---
