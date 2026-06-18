"""Host management: SSH probe, worker deploy/destroy, Fernet credential encryption."""
import asyncio
import os
import re
import shlex
from datetime import datetime, timezone

import paramiko
from cryptography.fernet import Fernet

from backend.db import db


def _get_fernet() -> Fernet:
    key = os.environ.get("HOST_SECRET_KEY", "")
    if not key:
        raise RuntimeError("HOST_SECRET_KEY env var not set")
    return Fernet(key.encode())


def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def _ssh_run_sync(host: str, port: int, username: str,
                  password: str, cmd: str) -> str:
    client = paramiko.SSHClient()
    client.load_system_host_keys()  # load ~/.ssh/known_hosts
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        try:
            client.connect(host, port=port, username=username,
                           password=password, timeout=10,
                           look_for_keys=False, allow_agent=False)
        except paramiko.ssh_exception.SSHException as e:
            if "not found in known_hosts" in str(e) or "Server" in str(e):
                raise RuntimeError(
                    f"Host key for {host} not trusted. "
                    f"Run: ssh-keyscan -H {host} >> ~/.ssh/known_hosts on the platform host"
                ) from e
            raise
        _, stdout, stderr = client.exec_command(cmd, timeout=30)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            raise RuntimeError(f"SSH command failed (exit {exit_code}): {err}")
        return out
    finally:
        client.close()


async def _ssh_run(host: str, port: int, username: str,
                   password: str, cmd: str) -> str:
    return await asyncio.to_thread(
        _ssh_run_sync, host, port, username, password, cmd
    )


async def add_host(label: str, host: str, port: int,
                   username: str, password: str) -> dict:
    password_enc = _encrypt(password)
    row = await db.insert_host(label, host, port, username, password_enc)
    row.pop("password_enc", None)
    return row


async def list_hosts() -> list[dict]:
    rows = await db.list_hosts()
    result = []
    for r in rows:
        r = dict(r)
        r.pop("password_enc", None)
        # Count running workers for this host
        workers = await db.list_remote_workers(host_id=r["id"], status="running")
        r["worker_count"] = len(workers)
        result.append(r)
    return result


async def delete_host(host_id: int) -> None:
    # Destroy all running workers first
    workers = await db.list_remote_workers(host_id=host_id, status="running")
    for w in workers:
        try:
            await destroy_worker(host_id, w["worker_id"])
        except Exception:
            pass
    await db.delete_host(host_id)


def _parse_nvidia_smi(raw: str) -> list[dict]:
    """Parse: nvidia-smi --query-gpu=index,name,memory.total,memory.free,utilization.gpu --format=csv,noheader,nounits"""
    gpus = []
    for line in raw.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        idx, name, mem_total, mem_free, util = parts[:5]
        try:
            gpus.append({
                "index":          int(idx),
                "name":           name,
                "vram_total_mb":  int(mem_total),
                "vram_free_mb":   int(mem_free),
                "utilization_pct": int(util),
                "busy":           int(util) > 10,
            })
        except ValueError:
            pass
    return gpus


def _parse_free(raw: str) -> dict:
    """Parse: free -m  (Mem: line only)"""
    for line in raw.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            return {"total_mb": int(parts[1]), "used_mb": int(parts[2])}
    return {"total_mb": 0, "used_mb": 0}


def _parse_df(raw: str) -> dict:
    """Parse: df -BG /  (second line)"""
    lines = raw.strip().splitlines()
    if len(lines) < 2:
        return {"path": "/", "total_gb": 0, "used_gb": 0}
    parts = lines[1].split()
    return {
        "path":     parts[5] if len(parts) > 5 else "/",
        "total_gb": int(parts[1].rstrip("G")),
        "used_gb":  int(parts[2].rstrip("G")),
    }


def _parse_docker_ps(raw: str) -> list[dict]:
    """Parse docker ps output for isaac-sim containers."""
    containers = []
    for line in raw.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, status, gpu_env = parts[0], parts[1], parts[2]
        gpu_index = None
        m = re.search(r"NVIDIA_VISIBLE_DEVICES=(\d+)", gpu_env)
        if m:
            gpu_index = int(m.group(1))
        containers.append({
            "name":      name,
            "status":    status,
            "gpu_index": gpu_index,
        })
    return containers


def _parse_used_ports(raw: str) -> list[int]:
    """Parse ss -tlnp for numeric ports."""
    ports = set()
    for line in raw.strip().splitlines()[1:]:  # skip header
        m = re.search(r":(\d+)\s", line)
        if m:
            ports.add(int(m.group(1)))
    return sorted(ports)


async def probe_host(host_id: int) -> dict:
    row = await db.get_host(host_id)
    if not row:
        raise ValueError(f"Host {host_id} not found")
    password = _decrypt(row["password_enc"])
    ssh = dict(host=row["host"], port=row["port"],
               username=row["username"], password=password)

    try:
        gpu_raw, mem_raw, disk_raw, docker_raw, ports_raw = await asyncio.gather(
            _ssh_run(**ssh, cmd=(
                "nvidia-smi --query-gpu=index,name,memory.total,memory.free,"
                "utilization.gpu --format=csv,noheader,nounits"
            )),
            _ssh_run(**ssh, cmd="free -m"),
            _ssh_run(**ssh, cmd="df -BG /"),
            _ssh_run(**ssh, cmd=(
                "docker ps --format '{{.Names}}\t{{.Status}}\t{{.Env}}' "
                "2>/dev/null | grep -i isaac || true"
            )),
            _ssh_run(**ssh, cmd="ss -tlnp"),
        )
        return {
            "host_id":    host_id,
            "probed_at":  datetime.now(timezone.utc).isoformat(),
            "gpus":       _parse_nvidia_smi(gpu_raw),
            "memory":     _parse_free(mem_raw),
            "disk":       _parse_df(disk_raw),
            "containers": _parse_docker_ps(docker_raw),
            "used_ports": _parse_used_ports(ports_raw),
            "error":      None,
        }
    except Exception as e:
        return {
            "host_id":    host_id,
            "probed_at":  datetime.now(timezone.utc).isoformat(),
            "gpus": [], "memory": {}, "disk": {}, "containers": [],
            "used_ports": [],
            "error":      str(e),
        }


_EVAL_PYTHONPATH = os.environ.get(
    "EVAL_PYTHONPATH",
    "/workspaces/isaaclab_arena:/workspaces/isaaclab_arena/isaaclab_arena_environments",
)
_EVAL_ACTOR_MODULE = os.environ.get("EVAL_ACTOR_MODULE", "arena_actor")
_EVAL_ACTOR_CLASS  = os.environ.get("EVAL_ACTOR_CLASS",  "IsaacLabArenaActor")
_RAY_HEAD_IP       = os.environ.get("RAY_HEAD_IP", "127.0.0.1")


async def deploy_worker(host_id: int) -> dict:
    host_row = await db.get_host(host_id)
    if not host_row:
        raise ValueError(f"Host {host_id} not found")

    status = await probe_host(host_id)
    if status.get("error"):
        raise RuntimeError(f"Cannot probe host: {status['error']}")

    # Find first free GPU not already used by a running worker
    running = await db.list_remote_workers(host_id=host_id, status="running")
    used_gpus = {w["gpu_index"] for w in running}
    free_gpu = next(
        (g["index"] for g in status["gpus"] if not g["busy"] and g["index"] not in used_gpus),
        None,
    )
    if free_gpu is None:
        raise RuntimeError("No free GPU available on this host")

    worker_id       = await db.next_worker_id()
    http_port       = 8042 + worker_id
    livestream_port = 49200 + worker_id
    container_name  = f"isaac-lab-worker-{worker_id}"

    password = _decrypt(host_row["password_enc"])
    host_row = dict(host_row)
    ssh = dict(host=host_row["host"], port=host_row["port"],
               username=host_row["username"], password=password)

    docker_cmd = (
        f"docker run -d --runtime=nvidia --network=host "
        f"--name {container_name} "
        f"--gpus device={free_gpu} "
        f"--ulimit memlock=-1 --ulimit stack=67108864 "
        f"--shm-size=8g "
        f"-e NVIDIA_VISIBLE_DEVICES=0 "
        f"-e NVIDIA_DRIVER_CAPABILITIES=all "
        f"-e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y "
        f"-e WORKER_ID={worker_id} "
        f"-e HTTP_PORT={http_port} "
        f"-e LIVESTREAM_PORT={livestream_port} "
        f"-e EVAL_ACTOR_MODULE={shlex.quote(_EVAL_ACTOR_MODULE)} "
        f"-e EVAL_ACTOR_CLASS={shlex.quote(_EVAL_ACTOR_CLASS)} "
        f"-e EVAL_PYTHONPATH={shlex.quote(_EVAL_PYTHONPATH)} "
        f"-v /home/disk/ssl/isaac-sim5.0/cache/ov:/root/.cache/ov "
        f"-v /home/disk/ssl/isaacsim_assets:/isaac-sim/isaacsim_assets:ro "
        f"isaaclab_arena:latest "
        f"bash -c '"
        f"source /workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim/setup_python_env.sh && "
        f"/workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim/kit/python/bin/ray "
        f"start --address={_RAY_HEAD_IP}:6379 --num-gpus=1 --block'"
    )
    await _ssh_run(**ssh, cmd=docker_cmd)

    worker_row = await db.insert_remote_worker(
        host_id, worker_id, free_gpu, http_port, livestream_port, container_name
    )

    # Background health-check: poll docker inspect for up to 60 s
    asyncio.create_task(_wait_for_worker(host_row, worker_id, container_name, password))

    worker_row = dict(worker_row)
    worker_row.pop("password_enc", None)
    return worker_row


async def _register_ray_actor(worker_id: int, http_port: int, livestream_port: int) -> None:
    """Register a Ray actor for a newly running worker."""
    import os
    try:
        import ray
        from backend.base_actor import load_actor_class
        actor_module = os.environ.get("EVAL_ACTOR_MODULE", "arena_actor")
        actor_class  = os.environ.get("EVAL_ACTOR_CLASS",  "IsaacLabArenaActor")
        ActorClass   = load_actor_class(actor_module, actor_class)
        actor_name   = f"arena-worker-{worker_id}"
        try:
            ray.get_actor(actor_name, namespace="robot-eval")
        except Exception:
            _ISAAC_SIM = "/workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim"
            ActorClass.options(
                name=actor_name,
                namespace="robot-eval",
                lifetime="detached",
                num_gpus=1,
                runtime_env={"env_vars": {
                    "LD_LIBRARY_PATH": ":".join([
                        _ISAAC_SIM, f"{_ISAAC_SIM}/kit",
                        f"{_ISAAC_SIM}/kit/kernel/plugins",
                        f"{_ISAAC_SIM}/kit/plugins",
                        f"{_ISAAC_SIM}/kit/plugins/carb_gfx",
                        f"{_ISAAC_SIM}/kit/plugins/gpu.foundation",
                    ]),
                    "CARB_APP_PATH": f"{_ISAAC_SIM}/kit",
                    "ISAAC_PATH":    _ISAAC_SIM,
                    "EXP_PATH":      f"{_ISAAC_SIM}/apps",
                    "RESOURCE_NAME": "IsaacSim",
                    "LD_PRELOAD":    f"{_ISAAC_SIM}/kit/libcarb.so",
                }},
            ).remote(worker_id, http_port, livestream_port)
    except Exception as e:
        print(f"[host_manager] Ray actor registration failed for worker {worker_id}: {e}", flush=True)


async def _wait_for_worker(host_row: dict, worker_id: int,
                            container_name: str, password: str) -> None:
    ssh = dict(host=host_row["host"], port=host_row["port"],
               username=host_row["username"], password=password)
    for _ in range(12):  # 12 × 5 s = 60 s
        await asyncio.sleep(5)
        try:
            out = await _ssh_run(
                **ssh,
                cmd=f"docker inspect --format='{{{{.State.Status}}}}' {container_name}"
            )
            if out.strip() == "running":
                await db.update_worker_status(worker_id, "running")
                worker_row = await db.get_remote_worker(worker_id)
                if worker_row:
                    await _register_ray_actor(worker_id, worker_row["http_port"], worker_row["livestream_port"])
                return
            if out.strip() in ("exited", "dead"):
                await db.update_worker_status(worker_id, "error")
                return
        except Exception:
            pass
    await db.update_worker_status(worker_id, "error")


async def destroy_worker(host_id: int, worker_id: int) -> None:
    worker_row = await db.get_remote_worker(worker_id)
    if not worker_row:
        raise ValueError(f"Worker {worker_id} not found")
    host_row = await db.get_host(host_id)
    if not host_row:
        raise ValueError(f"Host {host_id} not found")

    password = _decrypt(host_row["password_enc"])
    ssh = dict(host=host_row["host"], port=host_row["port"],
               username=host_row["username"], password=password)
    container = worker_row["container_name"]
    try:
        await _ssh_run(**ssh, cmd=f"docker stop {container} && docker rm {container}")
    except Exception:
        pass  # Container may already be gone; mark stopped regardless
    await db.update_worker_status(worker_id, "stopped")
