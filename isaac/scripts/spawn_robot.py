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
            # まずは空中で関節が動くか見る
            disable_gravity=False,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=False,
            solver_position_iteration_count=8,
            solver_velocity_iteration_count=4,
        ),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.8),
        joint_pos={
            "revolute1": 0.0,
            "revolute2": 0.0,
        },
    ),
    actuators={
        "servo_joints": ImplicitActuatorCfg(
            joint_names_expr=["revolute1", "revolute2"],
            effort_limit_sim=5.0,
            velocity_limit_sim=10.0,
            stiffness=50.0,
            damping=5.0,
        ),
    },
)


def main():
    sim_cfg = sim_utils.SimulationCfg(dt=0.005)
    sim = SimulationContext(sim_cfg)

    # 地面
    ground_cfg = sim_utils.GroundPlaneCfg()
    ground_cfg.func("/World/defaultGroundPlane", ground_cfg)

    # ライト
    light_cfg = sim_utils.DomeLightCfg(
        intensity=3000.0,
        color=(1.0, 1.0, 1.0),
    )
    light_cfg.func("/World/Light", light_cfg)

    # ロボット
    robot = Articulation(robot_cfg)

    # カメラ
    sim.set_camera_view(
        eye=(1.5, 1.5, 1.2),
        target=(0.0, 0.0, 0.5),
    )

    sim.reset()

    print("====================================")
    print("Joint motion view")
    print("Joint names:", robot.joint_names)
    print("Body names:", robot.body_names)
    print("====================================")

    t = 0.0
    dt = sim.get_physics_dt()

    while simulation_app.is_running():
        target = torch.zeros_like(robot.data.joint_pos)

        # 目標角度 [rad]
        target[:, 0] = 0.6 * math.sin(2.0 * t)
        target[:, 1] = 0.6 * math.cos(2.0 * t)

        robot.set_joint_position_target(target)
        robot.write_data_to_sim()

        sim.step()
        robot.update(dt)

        t += dt


if __name__ == "__main__":
    main()
    simulation_app.close()