import gymnasium as gym

from . import agents

# Register Gym environment.
gym.register(
    id="OkiagariKoboshi-Getup-Direct-v0",
    entry_point=f"{__name__}.okiagari_getup_env:OkiagariGetupEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.okiagari_getup_env:OkiagariGetupEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:OkiagariGetupPPORunnerCfg",
    },
)
