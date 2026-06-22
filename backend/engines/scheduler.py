"""
GPU-aware job scheduler with pluggable backends.

Architecture (aligned with K8s concepts):
  - SchedulerBackend (abstract) ≈ kube-scheduler interface
  - RayScheduler (local)        ≈ built-in scheduler with priority + Bin Packing
  - K8sScheduler (remote)       ≈ delegates to Volcano/K8s API

Switch via env: SCHEDULER_BACKEND=ray (default) | k8s
"""
from __future__ import annotations
import abc
import asyncio
import heapq
import random
import time
import uuid
from dataclasses import dataclass, field

import structlog
import asyncpg

from backend.db.queries import jobs as jq, runs as rq, episodes as eq
from backend.runners.registry import get_runner

logger = structlog.get_logger(__name__)


# ─── Data Models ────────────────────────────────────────────────────────────────

@dataclass(order=True)
class PrioritizedJob:
    priority: int
    enqueue_time: float
    job_id: str = field(compare=False)
    num_gpus: int = field(compare=False, default=1)
    gpu_type: str = field(compare=False, default="")
    submitter: str = field(compare=False, default="")


@dataclass
class WorkerState:
    actor_name: str
    busy: bool = False
    gpu_type: str = ""
    free_memory_mb: int = 0
    total_memory_mb: int = 0
    gpu_count: int = 1
    node_id: str = ""


# ─── Abstract Backend ───────────────────────────────────────────────────────────

class SchedulerBackend(abc.ABC):
    """Abstract scheduler interface — implementations handle actual dispatch."""

    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def enqueue(self, job_id: str, priority: int = 5,
                      num_gpus: int = 1, gpu_type: str = "",
                      submitter: str = "") -> None: ...

    @abc.abstractmethod
    async def notify_free(self, actor_name: str) -> None: ...

    @abc.abstractmethod
    def queue_depth(self) -> int: ...


# ─── Ray Local Scheduler (Priority Heap + Bin Packing) ──────────────────────────

class RayScheduler(SchedulerBackend):
    """
    GPU-aware scheduler for Ray-based local/multi-node clusters.
    - Priority heap (lower number = higher priority)
    - Bin Packing: pick worker with least free resources that still satisfies request
    - Periodic GPU state refresh via actor.gpu_info()
    """

    def __init__(self, pool: asyncpg.Pool, workers_meta: list[dict]):
        self._pool = pool
        self._workers_meta = workers_meta
        self._job_heap: list[PrioritizedJob] = []
        self._heap_lock = asyncio.Lock()
        self._worker_state: dict[str, WorkerState] = {}
        self._running = False
        self._dispatch_event = asyncio.Event()

        for w in workers_meta:
            name = w["actor_name"]
            self._worker_state[name] = WorkerState(
                actor_name=name, gpu_count=1,
                node_id=w.get("node_id", ""),
            )

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._dispatch_loop())
        asyncio.create_task(self._refresh_worker_states_loop())
        logger.info("scheduler.started", backend="ray",
                    workers=len(self._workers_meta))

    async def enqueue(self, job_id: str, priority: int = 5,
                      num_gpus: int = 1, gpu_type: str = "",
                      submitter: str = "") -> None:
        item = PrioritizedJob(
            priority=priority, enqueue_time=time.time(),
            job_id=job_id, num_gpus=num_gpus,
            gpu_type=gpu_type, submitter=submitter,
        )
        async with self._heap_lock:
            heapq.heappush(self._job_heap, item)
        self._dispatch_event.set()
        logger.info("scheduler.enqueued", job_id=job_id, priority=priority)

    async def notify_free(self, actor_name: str) -> None:
        if actor_name in self._worker_state:
            self._worker_state[actor_name].busy = False
        self._dispatch_event.set()

    def queue_depth(self) -> int:
        return len(self._job_heap)

    # ── Dispatch Loop ──

    async def _dispatch_loop(self) -> None:
        try:
            while self._running:
                await self._dispatch_event.wait()
                self._dispatch_event.clear()
                await self._try_dispatch()
        except asyncio.CancelledError:
            return

    async def _try_dispatch(self) -> None:
        async with self._heap_lock:
            remaining = []
            while self._job_heap:
                item = heapq.heappop(self._job_heap)
                worker = self._match_worker(item)
                if worker:
                    self._worker_state[worker].busy = True
                    asyncio.create_task(self._run_job(item.job_id, worker))
                else:
                    remaining.append(item)
            self._job_heap = remaining
            heapq.heapify(self._job_heap)

    def _match_worker(self, item: PrioritizedJob) -> str | None:
        """Bin Packing: find the tightest-fit free worker."""
        candidates = []
        for name, state in self._worker_state.items():
            if state.busy:
                continue
            if item.gpu_type and state.gpu_type and state.gpu_type.lower() != item.gpu_type.lower():
                continue
            if state.gpu_count < item.num_gpus:
                continue
            score = state.free_memory_mb if state.free_memory_mb > 0 else state.total_memory_mb
            candidates.append((score, name))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    # ── Job Execution (preserved from original) ──

    async def _run_job(self, job_id: str, actor_name: str) -> None:
        try:
            job = await jq.get_job(self._pool, job_id)
            if not job or job["status"] == "cancelled":
                return

            run_id = uuid.uuid4().hex[:8]
            attempt = job.get("retry_count", 0)
            seed = random.randint(0, 2**31)

            if (pc := job.get("policy_config") or {}).get("_reproduce_seed") is not None:
                seed = int(pc["_reproduce_seed"])

            await jq.update_job_status(self._pool, job_id, "running")
            await rq.create_run(self._pool, id=run_id, job_id=job_id,
                                attempt=attempt, seed=seed)
            await rq.update_run(self._pool, run_id, status="running",
                                worker_id=_actor_worker_id(actor_name),
                                started_at=time.time())
            await jq.append_log(self._pool, job_id,
                                f"分配 {actor_name} (attempt {attempt}, priority {job.get('priority', 5)})")

            try:
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
                logger.info("job.done", job_id=job_id, run_id=run_id)

            except asyncio.TimeoutError:
                await _handle_failure(self._pool, job_id, run_id,
                                     "timeout", job, self)
            except Exception as exc:
                await _handle_failure(self._pool, job_id, run_id,
                                     str(exc), job, self)
        finally:
            await self.notify_free(actor_name)

    # ── GPU State Refresh ──

    async def _refresh_worker_states_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(10)
                await self._refresh_worker_states()
        except asyncio.CancelledError:
            return

    async def _refresh_worker_states(self) -> None:
        import ray
        for name, state in self._worker_state.items():
            try:
                actor = ray.get_actor(name, namespace="robot-eval")
                info = await asyncio.to_thread(
                    ray.get, actor.gpu_info.remote(), timeout=5)
                state.free_memory_mb = info.get("free_memory_mb", 0)
                state.total_memory_mb = info.get("total_memory_mb", 0)
                state.gpu_type = info.get("gpu_type", "")
            except Exception:
                pass


# ─── K8s / Volcano Scheduler ───────────────────────────────────────────────────

class K8sScheduler(SchedulerBackend):
    """
    Delegates scheduling to Kubernetes + Volcano.
    Jobs are submitted as Volcano VcJob CRDs; K8s handles placement.
    """

    def __init__(self, pool: asyncpg.Pool, *, namespace: str = "robot-eval",
                 image: str = "isaaclab_arena:latest"):
        self._pool = pool
        self._namespace = namespace
        self._image = image
        self._queue_count = 0
        self._k8s_client = None

    async def start(self) -> None:
        try:
            from kubernetes import client, config as k8s_config
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()
            self._k8s_client = client.CustomObjectsApi()
            self._core_client = client.CoreV1Api()
            logger.info("scheduler.started", backend="k8s",
                        namespace=self._namespace)
        except ImportError:
            raise RuntimeError(
                "kubernetes package required for K8s backend. "
                "Install with: pip install kubernetes")

    async def enqueue(self, job_id: str, priority: int = 5,
                      num_gpus: int = 1, gpu_type: str = "",
                      submitter: str = "") -> None:
        job = await jq.get_job(self._pool, job_id)
        if not job:
            return

        vcjob = self._build_vcjob(job_id, job, priority=priority,
                                   num_gpus=num_gpus, gpu_type=gpu_type,
                                   submitter=submitter)
        await asyncio.to_thread(
            self._k8s_client.create_namespaced_custom_object,
            group="batch.volcano.sh", version="v1alpha1",
            namespace=self._namespace, plural="jobs",
            body=vcjob,
        )
        self._queue_count += 1
        await jq.update_job_status(self._pool, job_id, "submitted")
        await jq.append_log(self._pool, job_id,
                            f"提交到 K8s Volcano (priority={priority}, gpus={num_gpus})")
        logger.info("scheduler.k8s.submitted", job_id=job_id)

    async def notify_free(self, actor_name: str) -> None:
        self._queue_count = max(0, self._queue_count - 1)

    def queue_depth(self) -> int:
        return self._queue_count

    def _build_vcjob(self, job_id: str, job: dict, *,
                     priority: int, num_gpus: int,
                     gpu_type: str, submitter: str) -> dict:
        priority_map = {
            1: "critical", 2: "critical",
            3: "high", 4: "high",
            5: "normal", 6: "normal", 7: "normal",
            8: "low", 9: "low", 10: "low",
        }
        priority_class = priority_map.get(priority, "normal")
        queue_name = submitter if submitter else "default"

        config = job.get("config") or {}
        env_vars = [
            {"name": "JOB_ID", "value": job_id},
            {"name": "POLICY_TYPE", "value": config.get("policy_type", "zero_action")},
            {"name": "NUM_EPISODES", "value": str(config.get("num_episodes", 10))},
            {"name": "NUM_ENVS", "value": str(config.get("num_envs", 1))},
        ]
        if job.get("policy_server_url"):
            env_vars.append({"name": "POLICY_SERVER_URL",
                           "value": job["policy_server_url"]})

        node_selector = {}
        if gpu_type:
            node_selector["gpu-type"] = gpu_type

        return {
            "apiVersion": "batch.volcano.sh/v1alpha1",
            "kind": "Job",
            "metadata": {
                "name": f"eval-{job_id}",
                "labels": {
                    "app": "robot-eval",
                    "job-id": job_id,
                    "submitter": submitter or "unknown",
                },
            },
            "spec": {
                "queue": queue_name,
                "schedulerName": "volcano",
                "priorityClassName": priority_class,
                "minAvailable": 1,
                "maxRetry": job.get("max_retries", 3),
                "tasks": [{
                    "name": "eval",
                    "replicas": 1,
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "eval-worker",
                                "image": self._image,
                                "command": [
                                    "python", "-m",
                                    "backend.runners.isaaclab_runner",
                                    "--job-id", job_id,
                                ],
                                "env": env_vars,
                                "resources": {
                                    "limits": {
                                        "nvidia.com/gpu": str(num_gpus),
                                        "memory": "16Gi",
                                    },
                                    "requests": {
                                        "nvidia.com/gpu": str(num_gpus),
                                        "memory": "8Gi",
                                    },
                                },
                            }],
                            "nodeSelector": node_selector,
                            "restartPolicy": "OnFailure",
                        },
                    },
                }],
                "plugins": {
                    "sla": {"jobWaitingTime": f"{job.get('timeout_s', 3600)}s"},
                },
            },
        }

    async def watch_job_completion(self, job_id: str) -> None:
        """Poll K8s job status and update DB accordingly."""
        k8s_name = f"eval-{job_id}"
        while True:
            await asyncio.sleep(10)
            try:
                obj = await asyncio.to_thread(
                    self._k8s_client.get_namespaced_custom_object,
                    group="batch.volcano.sh", version="v1alpha1",
                    namespace=self._namespace, plural="jobs",
                    name=k8s_name,
                )
                state = obj.get("status", {}).get("state", {}).get("phase", "")
                if state == "Completed":
                    await jq.update_job_status(self._pool, job_id, "done")
                    await jq.append_log(self._pool, job_id, "K8s job completed")
                    break
                elif state == "Failed":
                    await jq.update_job_status(self._pool, job_id, "failed_final")
                    await jq.append_log(self._pool, job_id, "K8s job failed")
                    break
            except Exception as exc:
                logger.warning("k8s.watch_error", job_id=job_id, error=str(exc))
                break


# ─── Factory ────────────────────────────────────────────────────────────────────

def create_scheduler(pool: asyncpg.Pool, workers_meta: list[dict],
                     backend: str = "ray", **kwargs) -> SchedulerBackend:
    """Factory: create the appropriate scheduler backend."""
    if backend == "k8s":
        return K8sScheduler(pool, **kwargs)
    return RayScheduler(pool, workers_meta)


# ─── Shared Helpers ─────────────────────────────────────────────────────────────

def _build_runner(job: dict, actor_name: str):
    cfg = job.get("config") or {}
    config = {
        "actor_name":     actor_name,
        "arena_env_args": cfg.get("arena_env_args", {}),
        "num_envs":       cfg.get("num_envs", 1),
        "num_episodes":   cfg.get("num_episodes", 10),
        "num_steps":      cfg.get("num_steps"),
        "policy_type":    cfg.get("policy_type", "zero_action"),
        "policy_config":  job.get("policy_config") or {},
        "name":           job.get("name", ""),
    }
    if job.get("policy_server_url"):
        config["policy_server_url"] = job["policy_server_url"]
    runner = get_runner("isaaclab", config)
    return runner, config


async def _handle_failure(pool, job_id, run_id, error, job, scheduler):
    await rq.update_run(pool, run_id, status="failed",
                        error_msg=error, finished_at=time.time())
    retry_count = await jq.increment_retry(pool, job_id)
    if retry_count < job.get("max_retries", 3):
        backoff = 2 ** retry_count
        await jq.update_job_status(pool, job_id, "retry_pending")
        await jq.append_log(pool, job_id,
                            f"失败，{backoff}s 后重试 (attempt {retry_count})")

        async def _delayed_enqueue():
            await asyncio.sleep(backoff)
            current = await jq.get_job(pool, job_id)
            if current and current.get("status") not in ("cancelled", "failed_final"):
                await scheduler.enqueue(
                    job_id,
                    priority=job.get("priority", 5),
                    num_gpus=job.get("num_gpus", 1),
                    gpu_type=job.get("gpu_type", ""),
                )
        asyncio.create_task(_delayed_enqueue())
    else:
        await jq.update_job_status(pool, job_id, "failed_final")
        await jq.append_log(pool, job_id, f"ERROR: {error}")


def _actor_worker_id(actor_name: str) -> int:
    try:
        return int(actor_name.rsplit("-", 1)[-1])
    except ValueError:
        return 0


def _ep_to_dict(ep) -> dict:
    from dataclasses import asdict
    d = asdict(ep)
    if "index" in d:
        d["episode_index"] = d.pop("index")
    return d


# ─── Legacy Compatibility ───────────────────────────────────────────────────────
# Keep JobScheduler as alias for RayScheduler so existing tests don't break
JobScheduler = RayScheduler
