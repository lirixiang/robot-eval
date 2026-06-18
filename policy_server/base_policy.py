"""
PolicyBase — Abstract interface that external model providers implement.

The eval platform calls three endpoints on the policy server:
  GET  /info          → model metadata
  POST /reset         → start new episode
  POST /act           → get action given observation

Providers run their model as a FastAPI service (see server.py).
The platform connects via HTTP — no SDK dependency needed on the eval side.
"""
from abc import ABC, abstractmethod
from typing import Any, TypedDict


class PolicyInfo(TypedDict, total=False):
    model:       str   # model name, e.g. "pi0.5", "RDT-1B"
    version:     str   # version tag
    submitter:   str   # team / person name
    description: str   # free-form description
    paper_url:   str
    code_url:    str


class PolicyBase(ABC):
    """
    Implement this class and call serve(MyPolicy()) to expose your model.

    Observation dict keys depend on the environment, but common keys:
        rgb           np.ndarray  (H, W, 3) uint8 — wrist camera
        rgb_ext       np.ndarray  (H, W, 3) uint8 — external camera
        joint_pos     list[float]            — joint positions (rad)
        joint_vel     list[float]            — joint velocities (rad/s)
        ee_pos        list[float]  (3,)      — end-effector XYZ
        ee_quat       list[float]  (4,)      — end-effector quaternion WXYZ
        action_dim    int                    — expected action output size

    Action list size must equal observations["action_dim"].
    For a 7-DOF arm + gripper: 7 joint torques/velocities + 1 gripper = 8 values.
    """

    # Override with your model's metadata
    info: PolicyInfo = {}

    @abstractmethod
    def reset(self, episode_id: str, env_info: dict) -> None:
        """
        Called at the start of each episode.
        Use to reset any recurrent state (hidden states, history buffers, etc.).
        """

    @abstractmethod
    def act(self, observations: dict, episode_id: str, step: int) -> list[float]:
        """
        Given observations, return actions.
        observations["action_dim"] tells you the expected output size.
        """
