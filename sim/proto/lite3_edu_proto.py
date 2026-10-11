"""학생용 API 프로토타입. 실물 백엔드도 이 파일의 공통 로직(거리·각도 피드백, 속도 상한)을 그대로 쓴다."""
import atexit
import time

import numpy as np

import live
from lite3_sim import Lite3Sim, SIM_DT

MAX_SPEED = 0.4                 # m/s 명령값. 정책 추종률 약 75% → 실제 약 0.3 m/s (수업용 상한)
MAX_TURN = np.radians(40)       # rad/s
MIN_TURN = np.radians(26)       # 정책이 약 20°/s 미만 회전 명령에는 거의 반응하지 않음(측정값)
STOP_LEAD = 0.03                # m, 정지 명령 후 3–5 cm 더 미끄러지는 것을 고려
ANGLE_TOL = np.radians(2)


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


class Robot:
    def __init__(self, mode="mock", viewer=True):
        if mode != "mock":
            raise NotImplementedError("프로토타입은 mock 만 지원해요")
        self.viewer = None
        self._live = live.CONTEXT
        if self._live:                       # 이미 켜진 시뮬레이터에 연결 (코드 스튜디오 라이브 모드)
            self.sim = self._live.sim
            self._heading_goal = self.sim.rpy()[2]
            return
        self.sim = Lite3Sim()
        if viewer:
            import mujoco.viewer
            self.viewer = mujoco.viewer.launch_passive(self.sim.model, self.sim.data)
            self.viewer.cam.distance, self.viewer.cam.elevation = 2.5, -25
            atexit.register(self._keep_open)
        self._wall_start, self._sim_start = time.perf_counter(), self.sim.data.time

    # ---------- 학생이 쓰는 함수 ----------
    def stand(self):
        print("[로봇] 일어서기")
        self.sim.stand()
        self._run(lambda: self.sim.mode == "walk", timeout=5)
        self._hold(1.0)
        self._heading_goal = self.sim.rpy()[2]   # 이후 모든 이동·회전의 기준 방향

    def sit(self):
        print("[로봇] 멈추기")   # 프로토타입: 앉기 동작은 정지로 대신함
        self.sim.set_velocity(0, 0, 0)
        self._hold(1.0)

    def wait(self, sec):
        print(f"[로봇] {sec}초 기다리기")
        self._hold(sec)

    def forward(self, m):
        print(f"[로봇] 앞으로 {m} m")
        self._move(m, 0.0)

    def backward(self, m):
        print(f"[로봇] 뒤로 {m} m")
        self._move(-m, 0.0)

    def left(self, m):
        print(f"[로봇] 왼쪽으로 {m} m")
        self._move(0.0, m)

    def right(self, m):
        print(f"[로봇] 오른쪽으로 {m} m")
        self._move(0.0, -m)

    def turn_left(self, deg):
        print(f"[로봇] 왼쪽으로 {deg}도 돌기")
        self._turn(np.radians(deg))

    def turn_right(self, deg):
        print(f"[로봇] 오른쪽으로 {deg}도 돌기")
        self._turn(-np.radians(deg))

    def get_heading(self):
        return float(np.degrees(self.sim.rpy()[2]))

    def get_tilt(self):
        r, p, _ = np.degrees(self.sim.rpy())
        return float(r), float(p)

    def get_position(self):
        x, y, _ = self.sim.base_pos
        return float(x), float(y)

    # ---------- 무게중심 ----------
    def set_payload(self, kg, x=0.0, y=0.0):
        """(시뮬레이터 전용) 몸통 위에 kg 짜리 짐을 올린다. x: 앞(+)/뒤(−), y: 왼쪽(+)/오른쪽(−) [m]. 0 kg 이면 짐 내리기."""
        self.sim.set_payload(kg, x, y)
        self._hold(0.3)

    def get_com(self):
        """로봇 전체(짐 포함) 무게중심의 위치 (x, y, z) [m, 세계 좌표]."""
        return tuple(round(float(v), 4) for v in self.sim.com())

    def get_com_margin(self):
        """무게중심이 지지 다각형(바닥에 닿은 발들이 만드는 영역) 안쪽으로 몇 cm 들어와 있는지.
        음수면 밖 → 그대로 두면 넘어진다. 바닥에 닿은 발이 1개 이하면 None."""
        m = self.sim.support_info()["margin"]
        return None if m is None else round(m * 100, 1)

    # ---------- 공통 로직 (실물에서도 동일) ----------
    def _move(self, dx, dy):
        """목표 방향(self._heading_goal) 기준으로 (dx, dy)만큼 직선 이동.
        진행 거리 피드백 + 경로 이탈(옆 미끄러짐) 보정 + 방향 유지."""
        self._check_standing()
        yaw0 = self._heading_goal
        start = self.sim.base_pos[:2]
        dist = np.hypot(dx, dy)
        ux, uy = dx / dist, dy / dist          # 몸 좌표계 기준 진행 방향
        c, s = np.cos(yaw0), np.sin(yaw0)
        path = np.array([c * ux - s * uy, s * ux + c * uy])   # 세계 좌표계 진행 방향
        normal = np.array([-path[1], path[0]])

        def update():
            d = self.sim.base_pos[:2] - start
            remain = dist - d @ path
            off = d @ normal                    # 경로에서 왼쪽으로 벗어난 거리
            yaw = self.sim.rpy()[2]
            # 세계 좌표계 원하는 속도 = 진행 + 이탈 보정 → 몸 좌표계로 변환
            v = MAX_SPEED * path - np.clip(1.5 * off, -0.15, 0.15) * normal
            cy, sy = np.cos(-yaw), np.sin(-yaw)
            wz = np.clip(2.0 * _wrap(yaw0 - yaw), -MAX_TURN, MAX_TURN)
            self.sim.set_velocity(cy * v[0] - sy * v[1], sy * v[0] + cy * v[1], wz)
            return remain < STOP_LEAD

        self._run(update, timeout=dist / 0.05 + 5)
        self.sim.set_velocity(0, 0, 0)
        self._hold(0.5)

    def _check_standing(self):
        if self.sim.mode != "walk":
            raise RuntimeError("로봇이 서 있지 않아요. 먼저 dog.stand() 를 실행하세요.")

    def _turn(self, angle):
        """IMU yaw 피드백으로 회전. 멈춘 뒤 되돌아간 각도는 다시 보정한다."""
        self._check_standing()
        self._heading_goal = _wrap(self._heading_goal + angle)
        goal = self._heading_goal
        for _ in range(4):
            def update():
                err = _wrap(goal - self.sim.rpy()[2])
                wz = np.sign(err) * np.clip(2.0 * abs(err), MIN_TURN, MAX_TURN)
                self.sim.set_velocity(0, 0, wz)
                return abs(err) < ANGLE_TOL

            self._run(update, timeout=abs(angle) / np.radians(5) + 5)
            self.sim.set_velocity(0, 0, 0)
            self._hold(0.5)
            if abs(_wrap(goal - self.sim.rpy()[2])) < np.radians(3):
                return

    def _hold(self, sec):
        end = self.sim.data.time + sec
        self._run(lambda: self.sim.data.time >= end, timeout=sec + 1)

    def _run(self, done, timeout):
        """정책 주기(12 ms)마다 done()을 확인하며 시뮬을 진행한다."""
        end = self.sim.data.time + timeout
        while self.sim.data.time < end:
            if done():
                return
            self._advance(12)
            if self.sim.fallen():
                raise RuntimeError("로봇이 넘어졌어요! 프로그램을 멈춥니다.")
        raise TimeoutError("동작이 제한 시간 안에 끝나지 않았어요.")

    def _keep_open(self):
        """학생 프로그램이 끝나도 창을 닫을 때까지 로봇을 제자리에 세워 둔다."""
        if not self.viewer.is_running():
            return
        print("프로그램 끝! 창을 닫으면 종료됩니다.")
        self.sim.set_velocity(0, 0, 0)
        try:
            while True:
                self._advance(12)
        except SystemExit:
            pass

    def _advance(self, steps):
        if self._live:
            self._live.advance(steps)
            return
        for _ in range(steps):
            self.sim.step()
        self._sync_view()

    def _sync_view(self):
        if not self.viewer:
            return
        if not self.viewer.is_running():
            raise SystemExit("화면을 닫아서 프로그램을 종료합니다.")
        self.viewer.sync()
        lag = (self.sim.data.time - self._sim_start) - (time.perf_counter() - self._wall_start)
        if lag > 0:
            time.sleep(lag)    # 실제 시간 속도에 맞추기
