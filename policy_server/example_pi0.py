"""
Example: pi0 / pi0.5 adapter

Physical Intelligence's pi0 series outputs actions via their model API.
This wraps it to the RoboEval Policy Server interface.

Adapt this template to your actual pi0 inference code.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from policy_server import PolicyBase, serve


class Pi0Policy(PolicyBase):
    info = {
        "model":       "pi0.5",
        "version":     "0.5",
        "submitter":   "Physical Intelligence",
        "description": "pi0.5 diffusion policy for robot manipulation",
        "paper_url":   "https://www.physicalintelligence.company/blog/pi05",
    }

    def __init__(self, checkpoint_path: str):
        # Load your pi0 model here
        # from openpi.policies import pi0_policy
        # self.model = pi0_policy.Pi0Policy.from_checkpoint(checkpoint_path)
        self.checkpoint_path = checkpoint_path
        self._history: list = []

    def reset(self, episode_id: str, env_info: dict) -> None:
        self._history = []
        self.action_dim = env_info.get("action_dim", 8)
        # self.model.reset()  # reset recurrent state if needed

    def act(self, observations: dict, episode_id: str, step: int) -> list[float]:
        # Convert observations to model input format
        # obs_dict = {
        #     "image":     np.array(observations["rgb"], dtype=np.uint8),
        #     "state":     np.array(observations["joint_pos"]),
        #     "language":  observations.get("language_instruction", "pick up the cube"),
        # }
        # actions = self.model.predict(obs_dict)
        # return actions.tolist()

        # Placeholder — replace with real inference
        return [0.0] * self.action_dim


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--port", type=int, default=7860)
    args = p.parse_args()
    serve(Pi0Policy(args.checkpoint), port=args.port)
