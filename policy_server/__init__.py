"""
RoboEval Policy Server SDK
==========================

External model providers implement PolicyBase and serve it with `serve()`.

Quickstart
----------
    from policy_server import PolicyBase, serve

    class MyPolicy(PolicyBase):
        info = {"model": "my-model-v1", "submitter": "My Lab", "description": "..."}

        def reset(self, episode_id: str, env_info: dict) -> None:
            self.step = 0

        def act(self, observations: dict, episode_id: str, step: int) -> list[float]:
            return [0.0] * observations.get("action_dim", 7)

    serve(MyPolicy())

Then set `policy_server_url = "http://<your-host>:<port>"` when submitting jobs.
"""
from .base_policy import PolicyBase, PolicyInfo
from .server import serve

__all__ = ["PolicyBase", "PolicyInfo", "serve"]
