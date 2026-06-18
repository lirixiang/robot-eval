from __future__ import annotations
import asyncio, logging, random, time, uuid
import asyncpg
from backend.elo.calculator import update_glicko2, draw_glicko2
from backend.elo.significance import bootstrap_ci, SignificanceResult
from backend.db.queries import matches as mq, elo as eq

logger = logging.getLogger(__name__)

# Default judge config used when not specified
_DEFAULT_JUDGE = {
    "type":   "metric_compare",
    "metric": "success_rate",
    "min_diff": 0.02,
}

class ArenaEngine:
    def __init__(self, pool: asyncpg.Pool, job_engine):
        self._pool       = pool
        self._job_engine = job_engine  # JobEngine instance
        self._pending_tasks: set = set()

    async def create_match(
        self, *,
        env_name: str,
        model_a: str,
        model_b: str,
        template_id: int | None = None,
        mode: str = "direct",
        is_blind: bool = False,
        judge_config: dict | None = None,
        seed: int | None = None,
        arena_env_args: dict | None = None,
        num_episodes: int = 10,
        policy_server_url_a: str = "",
        policy_server_url_b: str = "",
    ) -> dict:
        """Create a match and dispatch two eval jobs (one per model)."""
        match_id  = uuid.uuid4().hex[:8]
        match_seed = seed if seed is not None else random.randint(0, 2**31)
        jcfg = judge_config or _DEFAULT_JUDGE

        match = await mq.create_match(
            self._pool, id=match_id, env_name=env_name,
            template_id=template_id, seed=match_seed, mode=mode,
            model_a=model_a, model_b=model_b,
            is_blind=is_blind, judge_config=jcfg,
        )

        env_args = {**(arena_env_args or {"environment": env_name}), "num_envs": 1}

        # Create eval jobs for model_a and model_b
        job_a = await self._job_engine.create_job(
            name=f"arena_{match_id}_a",
            model_name=model_a,
            arena_env_args=env_args,
            num_episodes=num_episodes,
            policy_server_url=policy_server_url_a,
            description=f"Arena match {match_id} (model A)",
        )
        job_b = await self._job_engine.create_job(
            name=f"arena_{match_id}_b",
            model_name=model_b,
            arena_env_args=env_args,
            num_episodes=num_episodes,
            policy_server_url=policy_server_url_b,
            description=f"Arena match {match_id} (model B)",
        )

        await mq.update_match(self._pool, match_id, status="running")
        match = await mq.get_match(self._pool, match_id)
        logger.info("arena.match_created", extra={
            "match_id": match_id, "model_a": model_a, "model_b": model_b,
        })

        # Background: wait for both jobs and judge
        task = asyncio.create_task(
            self._await_and_judge(match_id, job_a["id"], job_b["id"], env_name)
        )
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
        return match

    async def _await_and_judge(
        self, match_id: str, job_id_a: str, job_id_b: str, env_name: str
    ) -> None:
        """Wait for both jobs to finish, then judge and update Elo."""
        from backend.db.queries import jobs as jq, runs as rq, episodes as epq

        try:
            # Poll until both jobs are done (timeout: 2 hours)
            deadline = time.time() + 7200
            while time.time() < deadline:
                job_a = await jq.get_job(self._pool, job_id_a)
                job_b = await jq.get_job(self._pool, job_id_b)
                done_a = job_a and job_a["status"] in ("done", "failed_final", "cancelled")
                done_b = job_b and job_b["status"] in ("done", "failed_final", "cancelled")
                if done_a and done_b:
                    break
                await asyncio.sleep(10)
            else:
                await mq.update_match(self._pool, match_id, status="done",
                                       winner=None, finished_at=time.time())
                return

            run_a = await rq.latest_run_for_job(self._pool, job_id_a)
            run_b = await rq.latest_run_for_job(self._pool, job_id_b)

            match = await mq.get_match(self._pool, match_id)
            winner = None

            if run_a and run_b and run_a["status"] == "done" and run_b["status"] == "done":
                await mq.set_match_run(self._pool, match_id, "a", run_a["id"])
                await mq.set_match_run(self._pool, match_id, "b", run_b["id"])

                winner = _judge(
                    run_a["metrics"] or {}, run_b["metrics"] or {},
                    match["judge_config"] or _DEFAULT_JUDGE,
                )

                # Bootstrap significance test
                eps_a = await epq.get_episodes(self._pool, run_a["id"])
                eps_b = await epq.get_episodes(self._pool, run_b["id"])
                sig = bootstrap_ci(
                    [bool(e["success"]) for e in eps_a],
                    [bool(e["success"]) for e in eps_b],
                )
                logger.info("arena.significance", extra={
                    "match_id": match_id,
                    "significant": sig.significant,
                    "ci": f"[{sig.ci_low}, {sig.ci_high}]",
                })

                # Update Elo ratings
                await self._update_elo(
                    match_id, env_name,
                    match["model_a"], match["model_b"], winner,
                )

            await mq.update_match(
                self._pool, match_id,
                status="done", winner=winner, finished_at=time.time(),
            )
            logger.info("arena.match_done", extra={
                "match_id": match_id, "winner": winner,
            })

        except Exception as exc:
            logger.exception("arena.match_error", extra={
                "match_id": match_id, "error": str(exc),
            })
            await mq.update_match(self._pool, match_id, status="done",
                                   winner=None, finished_at=time.time())

    async def _update_elo(
        self, match_id: str, env_name: str,
        model_a: str, model_b: str, winner: str | None,
    ) -> None:
        player_a = await eq.get_or_create(self._pool, model_a, env_name)
        player_b = await eq.get_or_create(self._pool, model_b, env_name)

        if winner == "a":
            new_a, new_b = update_glicko2(player_a, player_b)
        elif winner == "b":
            new_b, new_a = update_glicko2(player_b, player_a)
        else:
            new_a, new_b = draw_glicko2(player_a, player_b)

        await eq.save(self._pool, model_a, env_name, new_a, match_id)
        await eq.save(self._pool, model_b, env_name, new_b, match_id)

    async def get_leaderboard(self, env_name: str) -> list[dict]:
        return await eq.list_leaderboard(self._pool, env_name)

    async def get_win_matrix(self, env_name: str) -> list[dict]:
        return await mq.win_matrix(self._pool, env_name)

    async def get_model_profile(self, model_name: str, env_name: str) -> dict:
        from backend.db.queries.matches import list_model_matches
        player   = await eq.get_or_create(self._pool, model_name, env_name)
        history  = await eq.get_history(self._pool, model_name, env_name)
        my_matches = await list_model_matches(self._pool, model_name, env_name)
        wins = sum(
            1 for m in my_matches if m.get("status") == "done" and (
                (m["model_a"] == model_name and m.get("winner") == "a") or
                (m["model_b"] == model_name and m.get("winner") == "b")
            )
        )
        return {
            "model_name":  model_name,
            "env_name":    env_name,
            "rating":      round(player.rating, 1),
            "rd":          round(player.rd, 1),
            "ci_low":      round(player.rating - 2 * player.rd, 1),
            "ci_high":     round(player.rating + 2 * player.rd, 1),
            "total_matches": len(my_matches),
            "wins":          wins,
            "history":       history,
        }

    async def list_envs_with_ratings(self) -> list[str]:
        return await eq.list_envs(self._pool)

    async def shutdown(self) -> None:
        """Cancel all pending match tasks on shutdown."""
        if self._pending_tasks:
            for task in list(self._pending_tasks):
                task.cancel()
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)


def _judge(metrics_a: dict, metrics_b: dict, config: dict) -> str:
    """Pure function: compare metrics and return 'a', 'b', or 'draw'."""
    metric   = config.get("metric", "success_rate")
    min_diff = float(config.get("min_diff", 0.02))
    val_a = float(metrics_a.get(metric, 0))
    val_b = float(metrics_b.get(metric, 0))
    diff  = val_a - val_b
    if abs(diff) < min_diff:
        return "draw"
    return "a" if diff > 0 else "b"


# Singleton — set by main.py lifespan
arena_engine: ArenaEngine | None = None
