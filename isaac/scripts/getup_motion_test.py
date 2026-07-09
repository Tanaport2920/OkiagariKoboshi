import argparse
import math

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import torch

import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.sim import SimulationContext


ROBOT_USD = "/workspace/OkiagariKoboshi_ws/assets/usd/okiagarikoboshi.usd"


robot_cfg = ArticulationCfg(
    prim_path="/World/OkiagariKoboshi",
    spawn=sim_utils.UsdFileCfg(
        usd_path=ROBOT_USD,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=False,
            solver_position_iteration_count=12,
            solver_velocity_iteration_count=4,
        ),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        # 少し高めから落として接触安定を見る
        pos=(0.0, 0.0, 0.35),
        joint_pos={
            "revolute1": 0.0,
            "revolute2": 0.0,
        },
    ),
    actuators={
        "servo_joints": ImplicitActuatorCfg(
            joint_names_expr=["revolute1", "revolute2"],
            effort_limit_sim=20.0,
            velocity_limit_sim=20.0,
            stiffness=120.0,
            damping=8.0,
        ),
    },
)


def get_target(t: float):
    """
    起き上がり候補モーション。
    ここを調整して、起き上がる動作を探す。
    angle unit: rad
    """

    # Phase 0: 接地して落ち着かせる
    if t < 0.5:
        q1 = 0.0
        q2 = 0.0

    # Phase 1: ため動作
    elif t < 1.0:
        a = (t - 0.5) / 0.5
        q1 = -0.8 * a
        q2 =  0.8 * a

    # Phase 2: 反動を作る
    elif t < 1.35:
        a = (t - 1.0) / 0.35
        q1 = -0.8 + 1.8 * a
        q2 =  0.8 - 1.8 * a

    # Phase 3: 支える/戻す
    elif t < 2.0:
        a = (t - 1.35) / 0.65
        q1 = 1.0 * (1.0 - a)
        q2 = -1.0 * (1.0 - a)

    # Phase 4: 中立
    else:
        q1 = 0.0
        q2 = 0.0

    return q1, q2


def main():
    sim_cfg = sim_utils.SimulationCfg(dt=0.005)
    sim = SimulationContext(sim_cfg)

    ground_cfg = sim_utils.GroundPlaneCfg()
    ground_cfg.func("/World/defaultGroundPlane", ground_cfg)

    light_cfg = sim_utils.DomeLightCfg(
        intensity=3000.0,
        color=(1.0, 1.0, 1.0),
    )
    light_cfg.func("/World/Light", light_cfg)

    robot = Articulation(robot_cfg)

    sim.set_camera_view(
        eye=(1.5, 1.5, 1.2),
        target=(0.0, 0.0, 0.2),
    )

    sim.reset()

    print("====================================")
    print("Get-up motion test")
    print("Joint names:", robot.joint_names)
    print("Body names:", robot.body_names)
    print("====================================")

    dt = sim.get_physics_dt()
    t = 0.0

    while simulation_app.is_running():
        # 4秒周期で繰り返す
        phase_t = t % 4.0

        q1, q2 = get_target(phase_t)

        target = torch.zeros_like(robot.data.joint_pos)
        target[:, 0] = q1
        target[:, 1] = q2

        robot.set_joint_position_target(target)
        robot.write_data_to_sim()

        sim.step()
        robot.update(dt)

        t += dt


if __name__ == "__main__":
    main()
    simulation_app.close()
