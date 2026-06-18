from __future__ import annotations
import asyncio, random, time, uuid, logging
import asyncpg
from backend.db.queries import jobs as jq, runs as rq, episodes as eq
from backend.runners.registry import get_runner

logger = logging.getLogger(__name__)

class JobScheduler:
    """
    Queue-based job dispatcher.
    - _job_queue: job_ids waiting for a free actor
    - _free_actors: actor names that just became free
    """

    def __init__(self, pool: asyncpg.Pool, workers_meta: list[dict]):
        self._pool        = pool
        self._workers     = workers_meta   # [{"worker_id": 0, "actor_name": "arena-worker-0", ...}]
        self._job_queue:  asyncio.Queue[str] = asyncio.Queue()
        self._free_actors: asyncio.Queue[str] = asyncio.Queue()
        self._running     = False

    async def start(self) -> None:
        self._running = True
        # Seed free actor queue with all known workers
        for w in self._workers:
            await self._free_actors.put(w["actor_name"])
        asyncio.create_task(self._dispatch_loop())
        logger.info("scheduler.started", extra={"workers": len(self._workers)})

    async def enqueue(self, job_id: str) -> None:
        await self._job_queue.put(job_id)
        logger.info("scheduler.enqueued", extra={"job_id": job_id})

    async def notify_free(self, actor_name: str) -> None:
        await self._free_actors.put(actor_name)

    async def _dispatch_loop(self) -> None:
        try:
            while self._running:
                job_id     = await self._job_queue.get()
                actor_name = await self._free_actors.get()
                asyncio.create_task(self._run_job(job_id, actor_name))
        except asyncio.CancelledError:
            return

    async def _run_job(self, job_id: str, actor_name: str) -> None:
        # Fix 2: wrap entire body in try/finally so actor is always returned
        try:
            job = await jq.get_job(self._pool, job_id)
            if not job or job["status"] == "cancelled":
                return   # actor freed in finally

            run_id  = uuid.uuid4().hex[:8]
            attempt = job.get("retry_count", 0)
            seed    = random.randint(0, 2**31)

            # Fix 4 (seed preservation): use _reproduce_seed from policy_config if present
            if (pc := job.get("policy_config") or {}).get("_reproduce_seed") is not None:
                seed = int(pc["_reproduce_seed"])

            await jq.update_job_status(self._pool, job_id, "running")
            await rq.create_run(self._pool, id=run_id, job_id=job_id,
                                 attempt=attempt, seed=seed)
            await rq.update_run(self._pool, run_id, status="running",
                                 worker_id=_actor_worker_id(actor_name),
                                 started_at=time.time())
            await jq.append_log(self._pool, job_id,
                                 f"分配 {actor_name} (attempt {attempt})")

            try:
                # Fix 1: _build_runner returns (runner, config); pass config to run()
                runner, run_config = _build_runner(job, actor_name)
                result = await asyncio.wait_for(
                    runner.run(run_config, seed=seed),
                    timeout=job.get("timeout_s", 3600),
                )
                t_end = time.time()
                await rq.update_run(
                    self._pool, run_id, status="done",
                    metrics=result.metrics,
                    elapsed_s=result.elapsed_s,
                    finished_at=t_end,
                )
                if result.episodes:
                    await eq.insert_episodes(
                        self._pool, run_id,
                        [_ep_to_dict(ep) for ep in result.episodes],
                    )
                await jq.update_job_status(self._pool, job_id, "done")
                await jq.append_log(self._pool, job_id,
                                      f"完成 metrics={result.metrics}")
                logger.info("job.done", extra={"job_id": job_id, "run_id": run_id})

            except asyncio.TimeoutError:
                await _handle_failure(self._pool, job_id, run_id,
                                       "timeout", job, self._job_queue)
            except Exception as exc:
                await _handle_failure(self._pool, job_id, run_id,
                                       str(exc), job, self._job_queue)
        finally:
            await self._free_actors.put(actor_name)

def _build_runner(job: dict, actor_name: str):
    """Build the appropriate runner for this job. Returns (runner, config_for_run)."""
    cfg = job.get("config") or {}          # read persisted config
    policy_url = job.get("policy_server_url", "")
    config = {
        "actor_name":    actor_name,
        "arena_env_args": cfg.get("arena_env_args", {}),
        "num_envs":      cfg.get("num_envs", 1),
        "num_episodes":  cfg.get("num_episodes", 10),
        "num_steps":     cfg.get("num_steps"),
        "policy_type":   cfg.get("policy_type", "zero_action"),
        "policy_config": job.get("policy_config") or {},
        "name":          job.get("name", ""),
    }
    if policy_url:
        config["policy_server_url"] = policy_url
    runner = get_runner("isaaclab", config)
    return runner, config

async def _handle_failure(pool, job_id, run_id, error, job, queue):
    await rq.update_run(pool, run_id, status="failed",
                         error_msg=error, finished_at=time.time())
    retry_count = await jq.increment_retry(pool, job_id)
    if retry_count < job.get("max_retries", 3):
        backoff = 2 ** retry_count
        await jq.update_job_status(pool, job_id, "retry_pending")
        await jq.append_log(pool, job_id,
                              f"失败，{backoff}s 后重试 (attempt {retry_count})")
        # Fix 3: schedule delayed re-enqueue without blocking the current actor
        async def _delayed_enqueue():
            await asyncio.sleep(backoff)
            await queue.put(job_id)
        asyncio.create_task(_delayed_enqueue())
    else:
        await jq.update_job_status(pool, job_id, "failed_final")
        await jq.append_log(pool, job_id, f"ERROR: {error}")

def _actor_worker_id(actor_name: str) -> int:
    try: return int(actor_name.rsplit("-", 1)[-1])
    except ValueError: return 0

def _ep_to_dict(ep) -> dict:
    from dataclasses import asdict
    d = asdict(ep)
    # Rename 'index' -> 'episode_index' to match insert_episodes schema
    if "index" in d:
        d["episode_index"] = d.pop("index")
    return d
