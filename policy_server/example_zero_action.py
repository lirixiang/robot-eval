"""
Example: Zero-action policy server (baseline)

Run:
    python example_zero_action.py

Then submit a job with:
    policy_server_url: "http://localhost:7860"
    policy_type: "remote"
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from policy_server import PolicyBase, serve


class ZeroActionPolicy(PolicyBase):
    info = {
        "model":       "zero-action-baseline",
        "version":     "1.0",
        "submitter":   "RoboEval Team",
        "description": "Outputs zero actions for all joints. Useful as a baseline.",
    }

    def reset(self, episode_id: str, env_info: dict) -> None:
        self.action_dim = env_info.get("action_dim", 8)

    def act(self, observations: dict, episode_id: str, step: int) -> list[float]:
        dim = observations.get("action_dim", getattr(self, "action_dim", 8))
        return [0.0] * dim


if __name__ == "__main__":
    serve(ZeroActionPolicy(), port=7860)
