from __future__ import annotations

import math
from collections.abc import Sequence

import torch

import isaaclab.sim as sim_utils
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.envs import DirectRLEnv, DirectRLEnvCfg
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sim import SimulationCfg
from isaaclab.sim.spawners.from_files import GroundPlaneCfg, spawn_ground_plane
from isaaclab.utils import configclass
from isaaclab.utils.math import euler_xyz_from_quat, quat_apply, quat_from_euler_xyz, sample_uniform
from .references.getup_reference import GETUP_REFERENCE

OKIAGARI_USD = "/workspace/OkiagariKoboshi_ws/assets/usd/okiagarikoboshi.usd"


OKIAGARI_CFG = ArticulationCfg(
    spawn=sim_utils.UsdFileCfg(
        usd_path=OKIAGARI_USD,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            max_depenetration_velocity=2.0,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=False,
            solver_position_iteration_count=12,
            solver_velocity_iteration_count=4,
        ),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.35),
        joint_pos={
            "revolute1": 0.0,
            "revolute2": 0.0,
        },
    ),
    actuators={
        "servos": ImplicitActuatorCfg(
            joint_names_expr=["revolute1", "revolute2"],
            effort_limit_sim=20.0,
            velocity_limit_sim=18.0,
            stiffness=120.0,
            damping=8.0,
        ),
    },
)


@configclass
class OkiagariGetupEnvCfg(DirectRLEnvCfg):
    """Direct RL task for a 2-DoF self-righting robot.

    Policy input is intentionally restricted to values obtainable on the real robot:
    base roll/pitch from IMU, base angular velocity from gyro, joint position/velocity
    from the two servos, the current servo target, and episode phase.
    """

    # 200 Hz physics, 50 Hz policy. M5Stack side should also run policy around 50 Hz.
    decimation = 4
    episode_length_s = 4.0
    action_space = 2
    observation_space = 13
    state_space = 0

    sim: SimulationCfg = SimulationCfg(dt=1.0 / 200.0, render_interval=decimation)

    robot_cfg: ArticulationCfg = OKIAGARI_CFG.replace(prim_path="/World/envs/env_.*/Robot")
    scene: InteractiveSceneCfg = InteractiveSceneCfg(num_envs=512, env_spacing=2.0, replicate_physics=True, clone_in_fabric=True)

    joint1_name = "revolute1"
    joint2_name = "revolute2"

    # Keep this enabled until all four randomized references have been verified.
    # Set to False for PPO training with policy actions.
    use_scripted_control = False

    # URDF limits were revolute1: +-1.5708, revolute2: +-2.0944.
    # Start slightly narrower for safety and sim stability.
    action_scale_1 = 1.20  # rad, action +1 -> +1.20 rad target for revolute1
    action_scale_2 = 1.50  # rad, action +1 -> +1.50 rad target for revolute2

    # Observation normalization. Keep identical values on M5Stack.
    gyro_scale = 0.25       # rad/s -> normalized. 4 rad/s maps to 1.
    joint_vel_scale = 0.10  # rad/s -> normalized. 10 rad/s maps to 1.

    # Reset settings.  Keep the four reference basins, but vary the drop pose
    # enough to train recovery from realistic off-axis orientations.
    init_root_height = 0.20
    init_height_noise = 0.08
    init_roll_noise = 0.25
    init_pitch_noise = 0.20
    init_yaw_noise = math.pi
    init_joint_noise = 0.15

    # Keep servos still while the robot is dropped and settles on the ground.
    # The get-up reference and policy phase start after this delay.
    drop_settle_time_s = 0.35

    # Reward weights.
    rew_alive = 0.05
    rew_upright = 4.0
    rew_height = 1.0
    rew_success = 5.0
    rew_ang_vel = -0.05
    rew_joint_vel = -0.005
    rew_action_rate = -0.02
    rew_action_mag = -0.001
    rew_reference = 4.0
    # Command imitation must dominate the tempting half-upright local optimum.
    rew_command_reference = 16.0
    # Once the body is nearly upright, the servos should return to the straight
    # standing posture instead of keeping one axis folded at its limit.
    rew_stand_joint_neutral = 16.0
    rew_stand_command_neutral = 20.0
    reference_error_scale = 0.5
    command_error_scale = 2.0
    stand_neutral_error_scale = 3.0

    # Policy actions are absolute normalized servo targets.  This is easier to
    # learn and matches what the real servo controller ultimately consumes.
    joint1_limit = 1.57
    joint2_limit = 2.09
    stand_joint_success_limit = 0.35
    stand_command_success_limit = 0.35

    # Servo specification: 60 degrees in 0.09 seconds.
    servo_speed_limit = math.radians(60.0) / 0.09

    # Termination safety.
    max_xy = 1.0
    min_height = -0.05
    max_ang_vel = 30.0


class OkiagariGetupEnv(DirectRLEnv):
    cfg: OkiagariGetupEnvCfg

    def __init__(self, cfg: OkiagariGetupEnvCfg, render_mode: str | None = None, **kwargs):
        super().__init__(cfg, render_mode, **kwargs)

        j1_ids, _ = self.robot.find_joints(self.cfg.joint1_name)
        j2_ids, _ = self.robot.find_joints(self.cfg.joint2_name)
        self._joint_ids = [j1_ids[0], j2_ids[0]]

        self.actions = torch.zeros(self.num_envs, 2, device=self.device)
        self.prev_actions = torch.zeros_like(self.actions)
        self.action_rate = torch.zeros_like(self.actions)
        self.joint_targets = torch.zeros_like(self.actions)

        self.joint_pos = self.robot.data.joint_pos
        self.joint_vel = self.robot.data.joint_vel

        # 0: roll_pos, 1: roll_neg, 2: pitch_pos, 3: pitch_neg
        self._mode_ids = torch.zeros(self.num_envs, dtype=torch.long, device=self.device)

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

    def _ensure_action_buffers(self):
        if not hasattr(self, "_actions"):
            self._actions = torch.zeros(self.num_envs, 2, device=self.device)

        if not hasattr(self, "_previous_actions"):
            self._previous_actions = torch.zeros(self.num_envs, 2, device=self.device)

        if not hasattr(self, "_servo_targets"):
            self._servo_targets = torch.zeros(self.num_envs, 2, device=self.device)

        if not hasattr(self, "_desired_targets"):
            self._desired_targets = torch.zeros(self.num_envs, 2, device=self.device)

    def _pre_physics_step(self, actions: torch.Tensor) -> None:
        self._ensure_action_buffers()
        self._previous_actions.copy_(self._actions)
        self._actions.copy_(torch.clamp(actions, -1.0, 1.0))

        # Keep the public buffers coherent for logging and compatibility.
        self.prev_actions.copy_(self.actions)
        self.actions.copy_(self._actions)
        self.action_rate.copy_(self.actions - self.prev_actions)

    def _get_episode_time(self) -> torch.Tensor:
        return self.episode_length_buf.float() * self.cfg.sim.dt * self.cfg.decimation

    def _get_task_time(self) -> torch.Tensor:
        return torch.clamp(self._get_episode_time() - self.cfg.drop_settle_time_s, min=0.0)

    def _control_active(self) -> torch.Tensor:
        return self._get_episode_time() >= self.cfg.drop_settle_time_s

    def _get_reference_target(self) -> torch.Tensor:
        """Return the interpolated teacher joint target for every environment."""
        t = self._get_task_time()
        target = torch.zeros(self.num_envs, 2, device=self.device)
        mode_names = ("roll_pos", "roll_neg", "pitch_pos", "pitch_neg")

        for mode_id, mode_name in enumerate(mode_names):
            env_mask = self._mode_ids == mode_id
            if not torch.any(env_mask):
                continue

            ref = GETUP_REFERENCE[mode_name]
            for i in range(len(ref) - 1):
                t0, q10, q20 = ref[i]
                t1, q11, q21 = ref[i + 1]
                mask = env_mask & (t >= t0) & (t < t1)
                alpha = torch.clamp((t - t0) / (t1 - t0), 0.0, 1.0)
                target[:, 0] = torch.where(mask, q10 + (q11 - q10) * alpha, target[:, 0])
                target[:, 1] = torch.where(mask, q20 + (q21 - q20) * alpha, target[:, 1])

            t_last, q1_last, q2_last = ref[-1]
            mask = env_mask & (t >= t_last)
            target[:, 0] = torch.where(mask, torch.full_like(t, q1_last), target[:, 0])
            target[:, 1] = torch.where(mask, torch.full_like(t, q2_last), target[:, 1])

        return target

    def _apply_action(self):
        self._ensure_action_buffers()

        if self.cfg.use_scripted_control:
            self._desired_targets.copy_(self._get_reference_target())
        else:
            self._desired_targets[:, 0] = self._actions[:, 0] * self.cfg.joint1_limit
            self._desired_targets[:, 1] = self._actions[:, 1] * self.cfg.joint2_limit

        # Do not move the servos while the robot is still falling/settling.
        active = self._control_active().unsqueeze(-1)
        self._desired_targets[:] = torch.where(
            active,
            self._desired_targets,
            torch.zeros_like(self._desired_targets),
        )

        # Apply the real-servo slew-rate limit at every physics step.  At 200 Hz
        # this is about 0.058 rad/step, or 0.233 rad per 50 Hz policy step.
        max_target_delta = self.cfg.servo_speed_limit * self.cfg.sim.dt
        target_delta = torch.clamp(
            self._desired_targets - self._servo_targets,
            -max_target_delta,
            max_target_delta,
        )
        self._servo_targets.add_(target_delta)

        self.robot.set_joint_position_target(
            self._servo_targets,
            joint_ids=self._joint_ids,
        )

        if self.common_step_counter % 50 == 0 and self._sim_step_counter % self.cfg.decimation == 0:
            print(
                "control debug:",
                "scripted=", self.cfg.use_scripted_control,
                "mode=", int(self._mode_ids[0].detach().cpu()),
                "active=", bool(active[0].detach().cpu()),
                "desired=", self._desired_targets[0].detach().cpu().numpy(),
                "target=", self._servo_targets[0].detach().cpu().numpy(),
                "joint_pos=", self.robot.data.joint_pos[0, self._joint_ids].detach().cpu().numpy(),
            )

    def _get_observations(self) -> dict:
        self._ensure_action_buffers()
        q = self.robot.data.root_quat_w
        roll, pitch, _ = euler_xyz_from_quat(q)
        ang_vel_b = self.robot.data.root_ang_vel_b

        joint_pos = self.robot.data.joint_pos[:, self._joint_ids]
        joint_vel = self.robot.data.joint_vel[:, self._joint_ids]
        task_time = self._get_task_time()
        task_length_s = max(self.cfg.episode_length_s - self.cfg.drop_settle_time_s, 1.0e-6)
        episode_phase = torch.clamp(task_time / task_length_s, 0.0, 1.0).unsqueeze(-1)

        obs = torch.cat(
            (
                torch.sin(roll).unsqueeze(-1),
                torch.cos(roll).unsqueeze(-1),
                torch.sin(pitch).unsqueeze(-1),
                torch.cos(pitch).unsqueeze(-1),
                ang_vel_b[:, 0:1] * self.cfg.gyro_scale,
                ang_vel_b[:, 1:2] * self.cfg.gyro_scale,
                (joint_pos[:, 0:1] / self.cfg.action_scale_1).clamp(-1.5, 1.5),
                (joint_pos[:, 1:2] / self.cfg.action_scale_2).clamp(-1.5, 1.5),
                joint_vel[:, 0:1] * self.cfg.joint_vel_scale,
                joint_vel[:, 1:2] * self.cfg.joint_vel_scale,
                self._servo_targets[:, 0:1] / self.cfg.joint1_limit,
                self._servo_targets[:, 1:2] / self.cfg.joint2_limit,
                episode_phase,
            ),
            dim=-1,
        )
        return {"policy": obs}

    def _get_rewards(self) -> torch.Tensor:
        root_quat = self.robot.data.root_quat_w
        root_ang_vel = self.robot.data.root_ang_vel_b
        root_pos = self.robot.data.root_pos_w
        joint_vel = self.robot.data.joint_vel[:, self._joint_ids]
        joint_pos = self.robot.data.joint_pos[:, self._joint_ids]

        self._ensure_action_buffers()
        active = self._control_active()

        x_body = torch.zeros(self.num_envs, 3, device=self.device)
        y_body = torch.zeros(self.num_envs, 3, device=self.device)
        z_body = torch.zeros(self.num_envs, 3, device=self.device)

        x_body[:, 0] = 1.0
        y_body[:, 1] = 1.0
        z_body[:, 2] = 1.0

        body_x_w = quat_apply(root_quat, x_body)
        body_y_w = quat_apply(root_quat, y_body)
        body_z_w = quat_apply(root_quat, z_body)

        x_z = body_x_w[:, 2]
        y_z = body_y_w[:, 2]
        z_z = body_z_w[:, 2]

        upright_raw = z_z

        # Keep root height for diagnostics only.  The articulation root is near
        # the ground in the physically upright pose (about 0.013 m), so root
        # height is not a valid get-up progress or success signal for this USD.
        height = root_pos[:, 2]
        height_score = torch.clamp(height / 0.13, 0.0, 1.0)

        # The body's local Z axis is the reliable upright signal: it is near 0
        # while lying sideways and near +1 after a successful get-up.  Squaring
        # the positive part keeps partial progress dense while emphasizing the
        # final portion of the motion.
        upright_score = torch.clamp(upright_raw, 0.0, 1.0)
        upright_reward = 12.0 * upright_score**2 * active.float()

        joint_neutral_error = (
            (joint_pos[:, 0] / self.cfg.joint1_limit) ** 2
            + (joint_pos[:, 1] / self.cfg.joint2_limit) ** 2
        )
        command_neutral_error = (
            (self._desired_targets[:, 0] / self.cfg.joint1_limit) ** 2
            + (self._desired_targets[:, 1] / self.cfg.joint2_limit) ** 2
        )
        stand_gate = torch.clamp((upright_score - 0.85) / 0.10, 0.0, 1.0) * active.float()
        stand_joint_neutral_reward = self.cfg.rew_stand_joint_neutral * stand_gate * (
            torch.exp(-self.cfg.stand_neutral_error_scale * joint_neutral_error) - 1.0
        )
        stand_command_neutral_reward = self.cfg.rew_stand_command_neutral * stand_gate * (
            torch.exp(-self.cfg.stand_neutral_error_scale * command_neutral_error) - 1.0
        )

        joint_near_neutral = torch.all(torch.abs(joint_pos) < self.cfg.stand_joint_success_limit, dim=1)
        command_near_neutral = torch.all(
            torch.abs(self._desired_targets) < self.cfg.stand_command_success_limit,
            dim=1,
        )

        # Root height cannot be used here: a visually successful standing pose
        # has a root height around 0.013 m in this model.  Success requires both
        # the body and the servos to be in the final straight standing posture.
        success = (upright_score > 0.95) & joint_near_neutral & command_near_neutral & active

        success_reward = 40.0 * success.float()

        # 暴れ抑制
        ang_vel_penalty = -0.02 * torch.sum(root_ang_vel[:, 0:2] ** 2, dim=1)
        joint_vel_penalty = -0.001 * torch.sum(joint_vel ** 2, dim=1)

        # 最初はaction penaltyをかなり弱くする
        action_penalty = -0.0001 * torch.sum(self._actions ** 2, dim=1)
        action_rate_penalty = -0.002 * torch.sum(
            (self._actions - self._previous_actions) ** 2,
            dim=1,
        )

        reference_target = self._get_reference_target()
        reference_error = torch.sum((joint_pos - reference_target) ** 2, dim=1)
        # Zero at perfect tracking and negative away from the reference.  The
        # previous positive-only form gave about 600 free points for staying at
        # zero during the reference's waiting periods, causing policy collapse.
        reference_reward = self.cfg.rew_reference * (
            torch.exp(-self.cfg.reference_error_scale * reference_error) - 1.0
        )

        # Immediate imitation signal for the policy command.  Physical joint
        # tracking alone forces PPO to infer servo lag and made close attempts
        # stall before reproducing the successful manual command trajectory.
        command_error = (
            ((self._desired_targets[:, 0] - reference_target[:, 0]) / self.cfg.joint1_limit) ** 2
            + ((self._desired_targets[:, 1] - reference_target[:, 1]) / self.cfg.joint2_limit) ** 2
        )
        command_reference_reward = self.cfg.rew_command_reference * (
            torch.exp(-self.cfg.command_error_scale * command_error) - 1.0
        )

        reward = (
            reference_reward
            + command_reference_reward
            + upright_reward
            + stand_joint_neutral_reward
            + stand_command_neutral_reward
            + success_reward
            + ang_vel_penalty
            + joint_vel_penalty
            + action_penalty
            + action_rate_penalty
        )

        if self.common_step_counter % 100 == 0:
            print(
                "axis debug env0:",
                "x_z=", float(x_z[0].detach().cpu()),
                "y_z=", float(y_z[0].detach().cpu()),
                "z_z=", float(z_z[0].detach().cpu()),
                "height=", float(height[0].detach().cpu()),
                "height_score=", float(height_score[0].detach().cpu()),
                "upright=", float(upright_raw[0].detach().cpu()),
                "success=", bool(success[0].detach().cpu()),
                "active=", bool(active[0].detach().cpu()),
                "ref_error=", float(reference_error[0].detach().cpu()),
                "ref_reward=", float(reference_reward[0].detach().cpu()),
                "cmd_error=", float(command_error[0].detach().cpu()),
                "cmd_reward=", float(command_reference_reward[0].detach().cpu()),
                "stand_joint_err=", float(joint_neutral_error[0].detach().cpu()),
                "stand_cmd_err=", float(command_neutral_error[0].detach().cpu()),
                "joint_pos=", self.robot.data.joint_pos[0, self._joint_ids].detach().cpu().numpy(),
            )

        return reward

    def _get_dones(self) -> tuple[torch.Tensor, torch.Tensor]:
        root_pos = self.robot.data.root_pos_w
        root_ang_vel_b = self.robot.data.root_ang_vel_b

        time_out = self.episode_length_buf >= self.max_episode_length - 1
        fallen_through = root_pos[:, 2] < self.cfg.min_height
        too_far = torch.any(torch.abs(root_pos[:, 0:2] - self.scene.env_origins[:, 0:2]) > self.cfg.max_xy, dim=1)
        too_fast = torch.any(torch.abs(root_ang_vel_b) > self.cfg.max_ang_vel, dim=1)
        terminated = fallen_through | too_far | too_fast
        return terminated, time_out

    def _reset_idx(self, env_ids: Sequence[int] | None):
        if env_ids is None:
            env_ids = self.robot._ALL_INDICES
        super()._reset_idx(env_ids)

        n = len(env_ids)
        device = self.device

        # Randomize equally across the four teacher-reference start poses.
        root_state = self.robot.data.default_root_state[env_ids].clone()
        root_state[:, 0:3] = self.scene.env_origins[env_ids]
        root_state[:, 2] += self.cfg.init_root_height + sample_uniform(
            0.0, self.cfg.init_height_noise, (n,), device
        )

        mode_ids = torch.randint(0, 4, (n,), device=device)
        self._mode_ids[env_ids] = mode_ids

        roll = torch.zeros(n, device=device)
        pitch = torch.zeros(n, device=device)
        yaw = torch.zeros(n, device=device)
        # These signs follow the pose naming used while the four references were
        # validated manually.  The simulator Euler sign appears reversed when
        # viewed from that convention, so keep the successful references fixed
        # and adapt only the reset pose mapping here.
        roll[mode_ids == 0] = -0.5 * math.pi  # roll_pos
        roll[mode_ids == 1] = 0.5 * math.pi   # roll_neg
        pitch[mode_ids == 2] = -0.5 * math.pi  # pitch_pos
        pitch[mode_ids == 3] = 0.5 * math.pi   # pitch_neg

        roll += sample_uniform(
            -self.cfg.init_roll_noise,
            self.cfg.init_roll_noise,
            (n,),
            device,
        )
        pitch += sample_uniform(
            -self.cfg.init_pitch_noise,
            self.cfg.init_pitch_noise,
            (n,),
            device,
        )
        yaw += sample_uniform(
            -self.cfg.init_yaw_noise,
            self.cfg.init_yaw_noise,
            (n,),
            device,
        )
        root_state[:, 3:7] = quat_from_euler_xyz(roll, pitch, yaw)
        root_state[:, 7:13] = 0.0

        joint_pos = self.robot.data.default_joint_pos[env_ids].clone()
        joint_vel = self.robot.data.default_joint_vel[env_ids].clone()
        joint_pos[:, self._joint_ids] += sample_uniform(-self.cfg.init_joint_noise, self.cfg.init_joint_noise, (n, 2), device)
        joint_vel[:, :] = 0.0

        self.robot.write_root_pose_to_sim(root_state[:, :7], env_ids)
        self.robot.write_root_velocity_to_sim(root_state[:, 7:], env_ids)
        self.robot.write_joint_state_to_sim(joint_pos, joint_vel, None, env_ids)

        self.actions[env_ids] = 0.0
        self.prev_actions[env_ids] = 0.0
        self.action_rate[env_ids] = 0.0

        self._ensure_action_buffers()
        self._actions[env_ids] = 0.0
        self._previous_actions[env_ids] = 0.0
        self._servo_targets[env_ids] = 0.0
        self._desired_targets[env_ids] = 0.0
