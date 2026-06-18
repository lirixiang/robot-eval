"""
env_server.py — Isaac Sim 内部运行的分布式评测服务器
合并了两个职责：
  1. TCP env_server：接受 eval_runner 连接，提供 reset/step/close 接口
  2. MJPEG frame_server：推流到浏览器

端口由环境变量控制，支持多 worker 并行：
  ENV_SERVER_PORT  = 50000  (eval 协议 TCP)
  FRAME_PORT       = 8765   (MJPEG HTTP)
  EVAL_TASK        = LiftObj
  EVAL_LAYOUT      = robocasakitchen-9-8
  WORKER_ID        = 0
"""
import io
import json
import os
import queue
import socket
import threading
import time
import traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ENV_PORT   = int(os.environ.get("ENV_SERVER_PORT", 50000))
FRAME_PORT = int(os.environ.get("FRAME_PORT", 8765))
WORKER_ID  = int(os.environ.get("WORKER_ID", 0))

# ── Bootstrap Isaac Sim ───────────────────────────────────────────────────────
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True, "anti_aliasing": 0})

import numpy as np
import omni.replicator.core as rep
from omni.isaac.core import World
from omni.isaac.core.objects import DynamicCuboid

# ── Scene setup ───────────────────────────────────────────────────────────────
world = World()
world.scene.add_default_ground_plane()
cube = world.scene.add(DynamicCuboid(
    prim_path="/World/Cube", name="cube",
    position=np.array([0.0, 0.0, 0.5]),
    size=0.3, color=np.array([0.2, 0.5, 1.0]),
))
world.reset()

# Render product for MJPEG
render_product = rep.create.render_product("/OmniverseKit_Persp", (1280, 720))
rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb")
rgb_annot.attach([render_product])

# ── Shared state between threads and sim loop ─────────────────────────────────
_frame_lock  = threading.Lock()
_current_jpeg = None

# Sim command queue: env_server puts cmds here, main loop processes them
_cmd_queue    = queue.Queue(maxsize=1)
_result_queue = queue.Queue(maxsize=1)

def _update_frame():
    global _current_jpeg
    try:
        data = rgb_annot.get_data()
        if data is None or data.size == 0:
            return
        from PIL import Image
        img = Image.fromarray(data[:, :, :3])
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=75)
        with _frame_lock:
            _current_jpeg = buf.getvalue()
    except Exception:
        traceback.print_exc()

# ── MJPEG HTTP server (background thread) ────────────────────────────────────
class FrameHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while True:
                    with _frame_lock:
                        jpeg = _current_jpeg
                    if jpeg:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n")
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                    time.sleep(1/30)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "worker_id": WORKER_ID}).encode())
        else:
            self.send_response(404); self.end_headers()

def _run_frame_server():
    srv = ThreadingHTTPServer(("0.0.0.0", FRAME_PORT), FrameHandler)
    print(f"[worker-{WORKER_ID}] MJPEG frame server on :{FRAME_PORT}", flush=True)
    srv.serve_forever()

# ── Eval env_server (background thread) ──────────────────────────────────────
# Protocol: newline-delimited JSON over TCP
# Client → {"cmd": "reset"} | {"cmd": "step", "action": [...]} | {"cmd": "close"} | {"cmd": "status"}
# Server → {"obs": {...}, "info": {}} | {"obs":..., "reward":..., "terminated":..., "truncated":..., "info":{}}

def _handle_client(conn: socket.socket):
    f = conn.makefile("rw", buffering=1)
    try:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                f.write('{"error":"invalid json"}\n')
                continue

            cmd = msg.get("cmd", "")

            if cmd == "status":
                f.write(json.dumps({
                    "status": "ready", "worker_id": WORKER_ID,
                    "env_port": ENV_PORT, "frame_port": FRAME_PORT,
                }) + "\n")

            elif cmd == "reset":
                _cmd_queue.put({"cmd": "reset"})
                result = _result_queue.get(timeout=30)
                f.write(json.dumps(result) + "\n")

            elif cmd == "step":
                _cmd_queue.put({"cmd": "step", "action": msg.get("action", [])})
                result = _result_queue.get(timeout=30)
                f.write(json.dumps(result) + "\n")

            elif cmd == "close":
                f.write('{"status":"closed"}\n')
                break

            else:
                f.write(json.dumps({"error": f"unknown cmd: {cmd}"}) + "\n")

            f.flush()
    except Exception as e:
        print(f"[worker-{WORKER_ID}] client error: {e}", flush=True)
    finally:
        conn.close()

def _run_env_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", ENV_PORT))
    srv.listen(4)
    print(f"[worker-{WORKER_ID}] env_server on :{ENV_PORT}", flush=True)
    while True:
        conn, addr = srv.accept()
        print(f"[worker-{WORKER_ID}] client connected from {addr}", flush=True)
        threading.Thread(target=_handle_client, args=(conn,), daemon=True).start()

# ── Start background threads ──────────────────────────────────────────────────
threading.Thread(target=_run_frame_server, daemon=True).start()
threading.Thread(target=_run_env_server,   daemon=True).start()

# ── Sim loop (main thread) ────────────────────────────────────────────────────
print(f"[worker-{WORKER_ID}] simulation loop started", flush=True)
step = 0

def _obs_from_world() -> dict:
    """Extract observation. TODO: replace with your task's real obs."""
    pos, rot = cube.get_world_pose()
    vel = cube.get_linear_velocity()
    return {"cube_pos": pos.tolist(), "cube_rot": rot.tolist(), "cube_vel": vel.tolist()}

while simulation_app.is_running():
    world.step(render=True)
    step += 1

    # Capture frame every 3 steps
    if step % 3 == 0:
        _update_frame()

    # Process pending eval command (non-blocking)
    if not _cmd_queue.empty():
        try:
            msg = _cmd_queue.get_nowait()
        except queue.Empty:
            continue

        cmd = msg["cmd"]
        if cmd == "reset":
            world.reset()
            obs = _obs_from_world()
            _result_queue.put({"obs": obs, "info": {}})

        elif cmd == "step":
            # TODO: apply action to your robot/policy here
            # action = msg["action"]
            # robot.apply_action(action)
            world.step(render=False)  # extra physics step
            obs   = _obs_from_world()
            # TODO: compute real reward & termination from your task
            reward     = 0.0
            terminated = False
            truncated  = False
            info       = {}
            _result_queue.put({
                "obs": obs, "reward": reward,
                "terminated": terminated, "truncated": truncated,
                "info": info,
            })

simulation_app.close()
