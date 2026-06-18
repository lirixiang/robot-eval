from __future__ import annotations
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["configs"])

@router.get("/configs")
def get_configs():
    return {
        "environments": [
            "lift_object",
            "pick_and_place_maple_table",
            "kitchen_pick_and_place",
            "sorting",
            "press_button",
        ],
        "policy_types": ["zero_action", "rsl_rl", "replay_action"],
        "example_job": {
            "name": "lift_object_baseline",
            "arena_env_args": {
                "environment": "lift_object",
                "embodiment":  "franka_joint_pos",
            },
            "num_envs":     1,
            "num_episodes": 10,
            "policy_type":  "zero_action",
            "policy_config": {},
            "policy_server_url": "",
            "model_name": "",
            "submitter": "",
            "description": "",
        },
    }
