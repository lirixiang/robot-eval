"""
Isaac Sim MJPEG frame streamer.
Captures the Kit viewport and serves as MJPEG over HTTP on port 8765.
Run with: /isaac-sim/python.sh frame_server.py
"""
import io
import sys
import time
import threading
import traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# ── Kit / Isaac Sim bootstrap ─────────────────────────────────────────────────
from isaacsim import SimulationApp
simulation_app = SimulationApp({
    "headless": True,
    "anti_aliasing": 0,
    "width": 1280,
    "height": 720,
})

import omni
import omni.replicator.core as rep
from omni.isaac.core import World

# ── Simple scene ──────────────────────────────────────────────────────────────
world = World()
world.scene.add_default_ground_plane()

# Add a rotating cube so there's visible motion
from omni.isaac.core.objects import DynamicCuboid
import numpy as np
cube = world.scene.add(DynamicCuboid(
    prim_path="/World/Cube",
    name="cube",
    position=np.array([0.0, 0.0, 0.5]),
    size=0.3,
    color=np.array([0.2, 0.5, 1.0]),
))
world.reset()

# ── Replicator render product ─────────────────────────────────────────────────
render_product = rep.create.render_product("/OmniverseKit_Persp", (1280, 720))
rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb")
rgb_annot.attach([render_product])

# ── Shared frame buffer ───────────────────────────────────────────────────────
_frame_lock = threading.Lock()
_current_jpeg = None


def update_frame():
    global _current_jpeg
    data = rgb_annot.get_data()
    if data is None or data.size == 0:
        return
    try:
        from PIL import Image
        img = Image.fromarray(data[:, :, :3])
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=75)
        with _frame_lock:
            _current_jpeg = buf.getvalue()
    except Exception:
        traceback.print_exc()


# ── MJPEG HTTP handler ────────────────────────────────────────────────────────
class StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence request logs

    def do_GET(self):
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while True:
                    with _frame_lock:
                        jpeg = _current_jpeg
                    if jpeg:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                    time.sleep(1 / 30)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()


def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", 8765), StreamHandler)
    print("[frame_server] MJPEG server started on :8765", flush=True)
    server.serve_forever()


threading.Thread(target=run_server, daemon=True).start()

# ── Simulation loop ───────────────────────────────────────────────────────────
print("[frame_server] Starting simulation loop", flush=True)
step = 0
while simulation_app.is_running():
    world.step(render=True)
    step += 1
    if step % 3 == 0:  # capture every 3 sim steps (~10 fps capture overhead)
        update_frame()

simulation_app.close()
