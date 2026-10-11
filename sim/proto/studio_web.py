"""Lite3 Studio (웹 UI) — 코드 편집기와 3D 시뮬레이터를 한 창에서.

실행: ../../.venv/Scripts/python studio_web.py          (앱 창으로 열림, run_studio.bat 더블클릭과 같음)
      ../../.venv/Scripts/python studio_web.py --browser (기본 브라우저로 열기)
      ../../.venv/Scripts/python studio_web.py --no-window --port 8765 (서버만, 시험용)

구조:
  [앱 창: web/index.html]  ⇄ WebSocket ⇄  [이 서버]  ⇄ stdin/stdout JSON ⇄  [sim_server.py --stream]
  화면은 three.js 로 로봇을 그리고, 물리 계산과 학생 코드 실행은 sim_server(MuJoCo)가 맡는다.
"""
import asyncio
import json
import os
import socket
import struct
import sys
import threading
import webbrowser
from pathlib import Path

import mujoco
import numpy as np
from aiohttp import WSMsgType, web

from lite3_joint_proto import (JOINT_INFO, JOINT_RANGE_DEG, LEG_NAMES, LEGS, POSES, SHANK, THIGH)
from lite3_sim import JOINT_NAMES, PAYLOAD_MAX, load_model

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
LESSONS = HERE / "joint_lessons"
SAVE_DIR = Path.home() / "Documents" / "Lite3Studio"
EVENT_PREFIX = "\x01EVT "
STOP_TIMEOUT = 3.0

SAMPLES = [
    ("basic", "기본 — 정사각형 걷기", HERE / "demo_square.py"),
    ("j1", "J1 — 모터 하나 움직이기", LESSONS / "j1_one_motor.py"),
    ("j2", "J2 — 자세 (엎드리기·서기·앉기)", LESSONS / "j2_poses.py"),
    ("j3", "J3 — 각도 ↔ 발 위치 (기구학)", LESSONS / "j3_kinematics.py"),
    ("j4", "J4 — 다리 하나 들기 (무게중심)", LESSONS / "j4_lift_leg.py"),
    ("j5", "J5 — 걸음새 직접 만들기 (트롯)", LESSONS / "j5_trot.py"),
]


# ---------------- 로봇 모델 (3D 화면용) ----------------
class Scene:
    """MuJoCo 모델에서 시각용 부품(group 2)의 메시와 배치를 꺼낸다. 물리 시뮬과 같은 모델을 쓴다."""

    def __init__(self):
        m = load_model()                     # 물리 시뮬과 같은 모델 (짐 상자 포함)
        self.meshes = {}
        geoms = []
        for g in range(m.ngeom):
            if m.geom_group[g] != 2:
                continue
            item = {"body": int(m.geom_bodyid[g]), "bodyName": m.body(m.geom_bodyid[g]).name,
                    "pos": m.geom_pos[g].round(6).tolist(), "quat": m.geom_quat[g].round(6).tolist()}
            if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
                mid = int(m.geom_dataid[g])
                item.update(type="mesh", mesh=mid)
                if mid not in self.meshes:
                    va, vn = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
                    fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
                    verts = m.mesh_vert[va:va + vn].astype("<f4")
                    faces = m.mesh_face[fa:fa + fn].astype("<u4")
                    self.meshes[mid] = struct.pack("<II", vn, fn) + verts.tobytes() + faces.tobytes()
            elif m.geom_type[g] == mujoco.mjtGeom.mjGEOM_SPHERE:
                item.update(type="sphere", radius=float(m.geom_size[g][0]))
            elif m.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX:
                item.update(type="box", size=[float(v) for v in m.geom_size[g]])
            else:
                continue
            geoms.append(item)
        self.info = {"nbody": int(m.nbody), "bodies": [m.body(i).name for i in range(m.nbody)], "geoms": geoms}


def meta():
    return {
        "samples": [{"id": sid, "name": name} for sid, name, _ in SAMPLES],
        "legs": LEGS, "legNames": LEG_NAMES, "joints": ["hip_x", "hip_y", "knee"],
        "jointInfo": {j: {"name": v[0], "meaning": v[1], "range": JOINT_RANGE_DEG[j]} for j, v in JOINT_INFO.items()},
        "officialNames": JOINT_NAMES,
        "poses": {k: [float(a) for leg in LEGS for a in (v[leg] if isinstance(v, dict) else v)] for k, v in POSES.items()},
        "thigh": THIGH, "shank": SHANK, "payloadMax": PAYLOAD_MAX,
    }


# ---------------- 시뮬레이터 프로세스 ----------------
class SimBridge:
    """sim_server.py --stream 을 띄우고, 웹 화면(WebSocket)들과 메시지를 주고받는다."""

    def __init__(self):
        self.proc = None
        self.clients = set()
        self.running = False
        self.run_id = 0
        self.last_state = None

    async def start(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8",
                   PYTHONPATH=os.pathsep.join([str(HERE), str(LESSONS)]))
        flags = 0x08000000 if sys.platform == "win32" else 0          # CREATE_NO_WINDOW
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, "-u", str(HERE / "sim_server.py"), "--stream",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            cwd=str(SAVE_DIR), env=env, creationflags=flags)
        asyncio.create_task(self._read(self.proc))

    async def _read(self, proc):
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
            if line.startswith(EVENT_PREFIX):
                ev = json.loads(line[len(EVENT_PREFIX):])
                name = ev.pop("event")
                if name in ("frame", "state"):
                    if name == "state":
                        self.last_state = ev
                    await self.broadcast({"type": name, **ev})
                    continue
                if name == "run_start":
                    self.running = True
                elif name == "run_end":
                    self.running = False
                await self.broadcast({"type": "event", "event": name, **ev})
            else:
                await self.broadcast({"type": "out", "text": line})
        await proc.wait()
        if proc is self.proc:                                         # 예상치 못한 종료 → 다시 켬
            was_running, self.running = self.running, False
            await self.broadcast({"type": "event", "event": "sim_restart", "wasRunning": was_running})
            await asyncio.sleep(0.3)
            await self.start()

    async def send(self, msg):
        if self.proc and self.proc.returncode is None:
            self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()

    async def stop(self):
        await self.send({"cmd": "stop"})
        run_id = self.run_id
        await asyncio.sleep(STOP_TIMEOUT)
        if self.running and run_id == self.run_id:                  # 응답 없음 → 시뮬레이터 재시작
            await self.broadcast({"type": "out", "text": "응답이 없어 시뮬레이터를 다시 시작해요.\n", "kind": "err"})
            self.proc.kill()

    async def broadcast(self, msg):
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_str(data)
            except ConnectionError:
                self.clients.discard(ws)

    async def handle(self, msg):
        kind = msg.get("type")
        if kind == "run":
            self.run_id += 1
            await self.send({"cmd": "run", "code": msg["code"]})
        elif kind == "stop":
            asyncio.create_task(self.stop())
        elif kind == "reset":
            await self.send({"cmd": "reset"})
        elif kind == "panel":
            await self.send({"cmd": "panel", **{k: v for k, v in msg.items() if k != "type"}})

    async def close(self):
        if self.proc and self.proc.returncode is None:
            proc, self.proc = self.proc, None
            proc.kill()


# ---------------- HTTP ----------------
def make_app():
    scene = Scene()
    bridge = SimBridge()
    app = web.Application()

    async def index(_):
        return web.FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})

    async def api_meta(_):
        return web.json_response(meta())

    async def api_scene(_):
        return web.json_response(scene.info)

    async def api_mesh(req):
        return web.Response(body=scene.meshes[int(req.match_info["mid"])], content_type="application/octet-stream")

    async def api_sample(req):
        for sid, _, path in SAMPLES:
            if sid == req.match_info["sid"]:
                return web.json_response({"code": path.read_text(encoding="utf-8")})
        raise web.HTTPNotFound()

    async def api_files(_):
        files = sorted(SAVE_DIR.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
        return web.json_response([p.name for p in files])

    def safe_path(name):
        name = Path(name).name
        if not name.endswith(".py"):
            name += ".py"
        return SAVE_DIR / name

    async def api_file_get(req):
        p = safe_path(req.match_info["name"])
        if not p.exists():
            raise web.HTTPNotFound()
        return web.json_response({"name": p.name, "code": p.read_text(encoding="utf-8")})

    async def api_file_save(req):
        body = await req.json()
        p = safe_path(body["name"])
        p.write_text(body["code"], encoding="utf-8")
        return web.json_response({"name": p.name, "path": str(p)})

    async def ws_handler(req):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(req)
        bridge.clients.add(ws)
        await ws.send_str(json.dumps({"type": "hello", "running": bridge.running}))
        if bridge.last_state:
            await ws.send_str(json.dumps({"type": "state", **bridge.last_state}))
        async for m in ws:
            if m.type == WSMsgType.TEXT:
                await bridge.handle(json.loads(m.data))
        bridge.clients.discard(ws)
        return ws

    async def on_startup(_):
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        await bridge.start()

    async def on_cleanup(_):
        await bridge.close()

    app.router.add_get("/", index)
    app.router.add_get("/api/meta", api_meta)
    app.router.add_get("/api/scene", api_scene)
    app.router.add_get("/api/mesh/{mid}", api_mesh)
    app.router.add_get("/api/sample/{sid}", api_sample)
    app.router.add_get("/api/files", api_files)
    app.router.add_get("/api/file/{name}", api_file_get)
    app.router.add_post("/api/file", api_file_save)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/web/", WEB)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(port, ready=None):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    runner = web.AppRunner(make_app())
    loop.run_until_complete(runner.setup())
    loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", port).start())
    if ready:
        ready.set()
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(runner.cleanup())


def main():
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1]) if "--port" in args else free_port()
    url = f"http://127.0.0.1:{port}/"
    if "--no-window" in args:
        print(url, flush=True)
        serve(port)
        return
    ready = threading.Event()
    threading.Thread(target=serve, args=(port, ready), daemon=True).start()
    ready.wait(15)
    if "--browser" not in args:
        try:
            import webview
            webview.create_window("Lite3 Studio", url, width=1440, height=900, min_size=(1100, 700),
                                  background_color="#0e1116", maximized=True)
            webview.start()
            return
        except Exception as e:  # pywebview 가 없거나 WebView2 가 없으면 브라우저로
            print("앱 창을 열 수 없어 브라우저로 엽니다:", e)
    webbrowser.open(url)
    threading.Event().wait()


if __name__ == "__main__":
    main()
