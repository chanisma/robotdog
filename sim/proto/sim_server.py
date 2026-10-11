"""라이브 시뮬레이터 서버 — 3D 창을 켜 둔 채 코드 스튜디오가 보내는 코드를 실행한다.

stdin  (한 줄에 JSON 하나): {"cmd": "run", "code": "..."} | {"cmd": "stop"} | {"cmd": "reset"} | {"cmd": "quit"}
       조작 패널: {"cmd": "panel", "op": "joints", "deg": [12개]} | {"op": "pose", "name": "stand"}
                 | {"op": "stiffness", "kp": 120} | {"op": "gait", "on": true, "T":0.4, "step":0.08, "lift":0.08, "height":-0.31}
stdout: 학생 코드의 print 출력, 그리고 EVENT_PREFIX 로 시작하는 상태 알림 줄
        ready / run_start / run_end(ok|error|stopped) / reset_done / busy / state(10 Hz: 관절각, 높이, 기울기, 발 힘)
학생 코드는 별도 스레드에서 실행하고, 물리 계산과 화면 갱신은 메인 스레드가 맡는다(live.py 참고).
"""
import ctypes
import json
import queue
import sys
import threading
import time
import traceback

import numpy as np

import live
from lite3_interface import Lite3SimInterface
from lite3_joint_proto import POSES, LEGS, inverse_kinematics, trot_feet
from lite3_sim import JOINT_KD, JOINT_LOWER, JOINT_UPPER, POS_COL, Lite3Sim, SIM_DT, make_joint_cmd

EVENT_PREFIX = "\x01EVT "
CODE_NAME = "내 코드"
IDLE_CHUNK = 12                      # 학생 코드가 없을 때도 12 ms 씩 물리를 진행 (로봇이 계속 균형을 잡음)
PANEL_RATE = np.radians(90) * 0.012   # 조작 패널: 관절이 12 ms 에 움직이는 최대 각도 (90°/s) → 갑자기 튀지 않음
SAFE_STAND_HEIGHT = 0.28              # 이보다 낮게 웅크리거나 엎드린 상태에서 서기·앉기는 먼저 엎드린 자세를 거친다
STATE_EVERY = 0.1                     # 상태 알림 주기 (초)
FRAME_EVERY = 1 / 30                  # 웹 3D 화면용 자세 전송 주기 (초)


def emit(event, **data):
    sys.stdout.write(EVENT_PREFIX + json.dumps({"event": event, **data}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class Server:
    def __init__(self, headless=False, stream=False):
        """headless: 화면 없이 최대 속도(시험용). stream: 창 없이 실시간으로 돌며 웹 화면용 frame 을 보냄."""
        self.sim = Lite3Sim()
        self.stream = stream
        self.last_frame = 0.0
        self.ctx = live.LiveContext(self.sim)
        live.CONTEXT = self.ctx
        self.commands = queue.Queue()
        self.worker = None
        self.code_running = False          # 학생 코드 실행 중 (run_end 를 알리기 직전에 False 가 됨)
        self.stop_requested_at = None
        self.injected = False
        self.robot = Lite3SimInterface(self.sim)    # 공식 인터페이스로 읽고 쓴다
        self.panel_goal = None                      # 조작 패널이 정한 목표각(rad 12개)
        self.panel_waypoints = []                   # 다음에 갈 목표각들 (서기 전에 엎드리기 등)
        self.panel_kp = 120.0
        self.gait = None                            # 조작 패널 걸음새 설정
        self.gait_t = 0.0
        self.last_state = 0.0
        self.viewer = None
        if not headless and not stream:
            import mujoco.viewer
            self.viewer = mujoco.viewer.launch_passive(self.sim.model, self.sim.data)
            self.viewer.cam.distance, self.viewer.cam.elevation = 2.2, -20

    # ---------- 명령 수신 ----------
    def _read_stdin(self):
        for line in sys.stdin:
            line = line.strip()
            if line:
                self.commands.put(json.loads(line))
        self.commands.put({"cmd": "quit"})

    def _handle(self, msg):
        cmd = msg.get("cmd")
        busy = self.code_running
        if cmd == "run":
            if busy:
                emit("busy")
            else:
                self.panel_goal, self.gait = None, None     # 이제 학생 코드가 로봇을 맡는다
                self.code_running = True
                self.worker = threading.Thread(target=self._run_code, args=(msg["code"],), daemon=True)
                self.worker.start()
        elif cmd == "stop" and busy:
            self.ctx.stop_flag = True                    # 다음 API 호출에서 StopRun 으로 멈춤
            self.stop_requested_at = time.perf_counter()
            self.injected = False
        elif cmd == "reset":
            if busy:
                emit("busy")
            else:
                with self.ctx.lock:
                    self.sim.reset()
                    self.panel_goal, self.gait = None, None
                emit("reset_done")
        elif cmd == "panel":
            if busy:
                emit("busy")
            else:
                with self.ctx.lock:
                    self._panel(msg)
        elif cmd == "quit":
            return False
        return True

    # ---------- 조작 패널 ----------
    def _panel(self, msg):
        op = msg.get("op")
        if op == "payload":                         # 짐은 보행 정책·관절 모드 어느 쪽이든 그대로 두고 바꾼다
            self.sim.set_payload(float(msg["kg"]), float(msg.get("x", 0)), float(msg.get("y", 0)))
            return
        self.robot.Start()                          # 관절 직접 제어 모드 (이미 그렇다면 그대로)
        current = self.robot.GetJointCommand()[:, POS_COL]
        self.panel_waypoints = []
        if op == "joints":
            self.panel_goal = np.radians(np.asarray(msg["deg"], dtype=np.float32))
            self.gait = None
        elif op == "pose":
            name = msg["name"]
            self.gait = None
            if name in ("stand", "sit") and (self.sim.base_pos[2] < SAFE_STAND_HEIGHT or self.sim.fallen()):
                # 공식 StandUp 상태처럼: 한쪽으로 쏠린 자세에서 바로 다리를 펴면 넘어지므로 먼저 엎드렸다가 일어선다
                self.panel_goal = self._pose_rad("lie")
                self.panel_waypoints = [self._pose_rad(name)]
            else:
                self.panel_goal = self._pose_rad(name)
        elif op == "stiffness":
            self.panel_kp = float(msg["kp"])
            if self.panel_goal is None:
                self.panel_goal = current.copy()
        elif op == "gait":
            if msg.get("on") and self.sim.fallen():
                emit("notice", text="로봇이 넘어져 있어요. ↺ 처음 자세를 누른 뒤 서기 → 걷기 순서로 해 보세요.")
            elif msg.get("on") and self.sim.base_pos[2] < 0.24:
                emit("notice", text="먼저 '서기'를 눌러 로봇을 세운 뒤 걸어 보세요.")
            elif msg.get("on"):
                if self.gait is None:
                    self.gait_t = 0.0                    # 걷는 중 값만 바꿀 때는 박자를 이어 간다
                self.gait = {k: float(msg[k]) for k in ("T", "step", "lift", "height")}
            else:
                self.gait = None
                self.panel_goal = current.copy()     # 멈춘 자리에서 그 자세 유지
        self.panel_goal = None if self.panel_goal is None else np.clip(self.panel_goal, JOINT_LOWER, JOINT_UPPER)

    @staticmethod
    def _pose_rad(name):
        pose = POSES[name]
        pose = pose if isinstance(pose, dict) else {leg: pose for leg in LEGS}
        return np.radians(np.array([pose[leg] for leg in LEGS], dtype=np.float32).reshape(-1))

    def _panel_tick(self):
        """학생 코드가 없을 때 12 ms 마다: 패널 목표를 향해 천천히 이동하거나 걸음새 진행."""
        if self.sim.mode != "joint" or (self.panel_goal is None and self.gait is None):
            return
        current = self.robot.GetJointCommand()[:, POS_COL]
        if self.gait:
            g = self.gait
            try:
                feet = trot_feet(self.gait_t, g["T"], g["step"], g["lift"], g["height"])
                q = current.reshape(4, 3).copy()
                for k, leg in enumerate(LEGS):
                    q[k, 1:] = np.radians(inverse_kinematics(*feet[leg]))
                target = q.reshape(-1)
            except ValueError:
                target = current
            self.gait_t += 0.012
        else:
            target = current + np.clip(self.panel_goal - current, -PANEL_RATE, PANEL_RATE)
            if self.panel_waypoints and np.max(np.abs(self.panel_goal - target)) < 1e-3                     and np.max(np.abs(self.robot.GetJointPosition() - target)) < np.radians(6):
                self.panel_goal = self.panel_waypoints.pop(0)     # 이번 자세에 도착 → 다음 자세로
        target = np.clip(target, JOINT_LOWER, JOINT_UPPER)
        self.robot.SetJointCommand(make_joint_cmd(target, self.panel_kp, JOINT_KD))

    def _emit_frame(self):
        """웹 3D 화면용: 바디 18개의 위치(xpos)와 회전(xquat, w x y z)."""
        d = self.sim.data
        info = self.sim.support_info()
        emit("frame", p=np.round(d.xpos, 4).reshape(-1).tolist(), q=np.round(d.xquat, 4).reshape(-1).tolist(),
             com=np.round(info["com"], 4).tolist(),
             sup=[[round(float(a), 4), round(float(b), 4)] for a, b in info["support"]],
             margin=None if info["margin"] is None else round(info["margin"], 4),
             pm=round(self.sim.payload[0], 2))

    def _com_state(self):
        """위에서 본 무게중심 그림용: 몸통 기준 좌표(x 앞, y 왼쪽, m)로 바꾼 발·무게중심·지지 다각형."""
        info = self.sim.support_info()
        c, s = np.cos(self.sim.rpy()[2]), np.sin(self.sim.rpy()[2])
        base = self.sim.base_pos[:2]

        def body(p):
            dx, dy = p[0] - base[0], p[1] - base[1]
            return [round(float(c * dx + s * dy), 4), round(float(-s * dx + c * dy), 4)]
        kg, px, py = self.sim.payload
        return {"com_b": body(info["com"]), "feet_b": [body(f) for f in info["feet"]],
                "sup_b": [body(q) for q in info["support"]], "contact": [bool(t) for t in info["contact"]],
                "margin": None if info["margin"] is None else round(info["margin"] * 100, 1),
                "payload": [round(kg, 2), round(px, 3), round(py, 3)]}

    def _emit_state(self):
        """조작 패널 표시용 상태 (공식 인터페이스로 읽음)."""
        fz = self.robot.GetContactForce().reshape(4, 3)[:, 2]
        emit("state",
             q=[round(float(a), 1) for a in np.degrees(self.robot.GetJointPosition())],
             target=[round(float(a), 1) for a in np.degrees(self.robot.GetJointCommand()[:, POS_COL])],
             rpy=[round(float(a), 1) for a in np.degrees(self.robot.GetImuRpy())],
             height=round(float(self.sim.base_pos[2]), 3),
             fz=[round(float(f), 1) for f in fz],
             mode=self.sim.mode,
             fallen=bool(self.sim.fallen()),
             **self._com_state(),
             gait=self.gait is not None,
             kp=self.panel_kp)

    # ---------- 학생 코드 실행 (작업 스레드) ----------
    def _run_code(self, code):
        self.ctx.lock.acquire()
        self.ctx.stop_flag = False
        self.stop_requested_at = None
        emit("run_start")
        status = "ok"
        try:
            exec(compile(code, CODE_NAME, "exec"), {"__name__": "__main__"})
        except live.StopRun:
            status = "stopped"
        except SystemExit:
            pass
        except BaseException as e:
            status = "error"
            # 서버 내부(exec 호출) 줄은 빼고 학생 코드부터 보여 준다
            traceback.print_exception(type(e), e, e.__traceback__.tb_next, file=sys.stdout)
        finally:
            try:
                self.sim.set_velocity(0, 0, 0)          # 걷던 중이면 제자리에 멈춤
            finally:
                self.ctx.stop_flag = False
                self.code_running = False
                self.ctx.lock.release()
            sys.stdout.flush()
            emit("run_end", status=status)

    def _force_stop_if_stuck(self):
        """정지를 눌렀는데 0.5초가 지나도 API 를 부르지 않는 계산(while True: pass 등)에 갇혀 있으면
        작업 스레드에 StopRun 예외를 한 번 주입한다. (API 대기 중일 때는 주입하지 않음)"""
        if (self.stop_requested_at is None or self.injected or self.worker is None
                or not self.code_running):
            return
        if time.perf_counter() - self.stop_requested_at > 0.5 and self.ctx.remaining == 0                 and self.ctx.stop_flag:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(self.worker.ident),
                                                       ctypes.py_object(live.StopRun))
            self.injected = True

    # ---------- 메인 루프: 물리 진행 + 화면 갱신 ----------
    def loop(self, max_seconds=None):
        threading.Thread(target=self._read_stdin, daemon=True).start()
        emit("ready")
        wall0, sim0 = time.perf_counter(), self.sim.data.time
        started = time.perf_counter()
        while self.viewer is None or self.viewer.is_running():
            if max_seconds and time.perf_counter() - started > max_seconds:
                break
            try:
                while True:
                    if not self._handle(self.commands.get_nowait()):
                        return
            except queue.Empty:
                pass

            self._force_stop_if_stuck()
            if not self.ctx.lock.acquire(timeout=0.005):
                continue                                 # 학생 코드가 계산 중 → 이번 차례는 건너뜀
            try:
                busy = self.code_running
                if not busy:
                    self._panel_tick()
                n = min(IDLE_CHUNK, self.ctx.remaining) if busy else IDLE_CHUNK
                for _ in range(n):
                    self.sim.step()
                if busy and n:
                    self.ctx.remaining -= n
                    if self.ctx.remaining == 0:
                        self.ctx.done.set()
                if self.viewer:
                    self.viewer.sync()
                if self.stream and time.perf_counter() - self.last_frame > FRAME_EVERY:
                    self.last_frame = time.perf_counter()
                    self._emit_frame()
                if time.perf_counter() - self.last_state > STATE_EVERY:
                    self.last_state = time.perf_counter()
                    self._emit_state()
            finally:
                self.ctx.lock.release()

            if self.viewer is None and not self.stream:  # 시험용 화면 없는 모드: 최대 속도
                continue
            lag = (self.sim.data.time - sim0) - (time.perf_counter() - wall0)
            if lag > 0:
                time.sleep(lag)                          # 실제 시간 속도에 맞추기
            elif lag < -0.2:
                wall0, sim0 = time.perf_counter(), self.sim.data.time   # 느린 PC: 밀린 시간은 버림
            if n == 0:
                time.sleep(0.001)


if __name__ == "__main__":
    Server(headless="--headless" in sys.argv, stream="--stream" in sys.argv).loop()
