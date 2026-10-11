"""학생용 관절(모터) 직접 조작 API 프로토타입 — 심화 과정.

DEEP Robotics 공식 인터페이스(lite3_interface.Lite3SimInterface = interface::RobotInterface) 위에
학생이 읽기 쉬운 이름과 도(°) 단위를 얹은 얇은 층이다. 내부에서는 모든 명령이
공식 형식 SetJointCommand(12×5: [kp, 목표각 rad, kd, 목표속도, 보조토크]) 로 나간다.

  다리: FL(앞왼쪽) FR(앞오른쪽) HL(뒤왼쪽) HR(뒤오른쪽)
  관절: hip_x = 공식 HipX (옆으로 벌리기), hip_y = HipY (앞뒤로 흔들기), knee = Knee (무릎)
  dog.set_angle("FL", "knee", 100)  →  공식 관절 2번 FL_Knee_joint 의 목표각 1.745 rad
  dog.robot                          →  공식 인터페이스를 직접 쓰고 싶을 때
"""
import atexit
import time

import numpy as np

import live
from lite3_interface import Lite3SimInterface
from lite3_sim import (JOINT_KD, JOINT_KP, JOINT_LOWER, JOINT_NAMES, JOINT_UPPER, POS_COL,
                       SIM_DT, Lite3Sim, make_joint_cmd)

LEGS = ["FL", "FR", "HL", "HR"]
JOINTS = ["hip_x", "hip_y", "knee"]
THIGH, SHANK = 0.20, 0.21          # m, Lite3.xml
FOOT_RADIUS = 0.022                # m
HIP_Y_OFFSET = 0.09735             # m, 엉덩이 관절에서 허벅지까지 옆 간격

LEG_NAMES = {"FL": "앞왼쪽", "FR": "앞오른쪽", "HL": "뒤왼쪽", "HR": "뒤오른쪽"}
JOINT_INFO = {   # 관절별 쉬운 이름과 부호의 뜻 (시뮬에서 측정해 확인함)
    "hip_x": ("옆으로 벌리기", "+ 값이면 발이 로봇의 오른쪽으로, − 값이면 왼쪽으로 (네 다리 모두 같은 방향)"),
    "hip_y": ("앞뒤로 흔들기", "+ 값이면 다리가 앞으로, − 값이면 뒤로 (서 있을 때 약 −37°)"),
    "knee":  ("무릎 굽히기", "값이 클수록 무릎을 많이 접어 발이 몸 쪽으로 올라옴 (서 있을 때 약 74°)"),
}
JOINT_RANGE_DEG = {j: (float(np.degrees(JOINT_LOWER[i])), float(np.degrees(JOINT_UPPER[i])))
                   for i, j in enumerate(("hip_x", "hip_y", "knee"))}

POSES = {   # 다리 하나의 (hip_x, hip_y, knee) [도]. 네 다리에 같은 값을 쓴다.
    "lie":   (0, -77.6, 146.1),     # 엎드리기 (공식 시뮬 초기 자세)
    "stand": (0, -37.2, 74.5),      # 서기 (공식 정책의 기본 자세 -0.65, 1.30 rad)
    "sit": {"FL": (0, -25, 50), "FR": (0, -25, 50), "HL": (0, -95, 150), "HR": (0, -95, 150)},  # 강아지 앉기
}


def official_name(leg, joint):
    """학생용 이름 → 공식 관절 번호와 이름. 예: ("FL", "knee") → (2, "FL_Knee_joint")"""
    i = _index(leg, joint)
    return i, JOINT_NAMES[i]


def _index(leg, joint):
    if leg not in LEGS:
        raise ValueError(f"다리 이름 '{leg}' 은(는) 없어요. 쓸 수 있는 이름: {', '.join(LEGS)}")
    if joint not in JOINTS:
        raise ValueError(f"관절 이름 '{joint}' 은(는) 없어요. 쓸 수 있는 이름: {', '.join(JOINTS)}")
    return LEGS.index(leg) * 3 + JOINTS.index(joint)


# ---------- 기구학 (다리 한 개, 옆에서 본 2차원) ----------
def forward_kinematics(hip_y_deg, knee_deg):
    """관절 각도 → 발끝 위치 (x: 앞+, z: 위+, 엉덩이 관절 기준, m)."""
    q1, q2 = np.radians(hip_y_deg), np.radians(knee_deg)
    x = THIGH * np.sin(q1) + SHANK * np.sin(q1 + q2)
    z = -(THIGH * np.cos(q1) + SHANK * np.cos(q1 + q2))
    return float(x), float(z)


def inverse_kinematics(x, z):
    """발끝 위치 → 관절 각도 (hip_y, knee) [도]. 무릎은 뒤로 접히는 쪽 해를 고른다."""
    r2 = x * x + z * z
    c = (r2 - THIGH**2 - SHANK**2) / (2 * THIGH * SHANK)
    if abs(c) > 1:
        raise ValueError(f"다리가 닿을 수 없는 위치예요: 거리 {np.sqrt(r2):.3f} m (최대 {THIGH + SHANK:.2f} m)")
    q2 = np.arccos(c)
    q1 = np.arctan2(x, -z) - np.arctan2(SHANK * np.sin(q2), THIGH + SHANK * np.cos(q2))
    return float(np.degrees(q1)), float(np.degrees(q2))



# ---------- 트롯 걸음새 (J5 와 같은 규칙, 조작 패널에서 사용) ----------
TROT_PHASE = {"FL": 0.0, "HR": 0.0, "FR": 0.5, "HL": 0.5}   # 대각선 짝


def trot_feet(t, T=0.4, step=0.08, lift=0.08, height=-0.31, x_offset=0.02):
    """시각 t 에서 네 발끝 위치 {다리: (x, z)}. 주기의 앞 절반은 딛기, 뒤 절반은 옮기기."""
    feet = {}
    for leg, phase in TROT_PHASE.items():
        p = (t / T + phase) % 1.0
        if p < 0.5:
            x, z = step / 2 - step * (p / 0.5), height
        else:
            s = (p - 0.5) / 0.5
            x, z = -step / 2 + step * s, height + lift * np.sin(np.pi * s)
        feet[leg] = (x + x_offset, z)
    return feet


class JointDog:
    def __init__(self, mode="mock", viewer=True):
        if mode != "mock":
            raise NotImplementedError("프로토타입은 mock 만 지원해요")
        self.viewer = None
        self._live = live.CONTEXT
        self.kp, self.kd = JOINT_KP, JOINT_KD
        if self._live:                       # 이미 켜진 시뮬레이터에 연결 (코드 스튜디오 라이브 모드)
            self.sim = self._live.sim
            self.robot = Lite3SimInterface(self.sim)
            self.robot.Start()               # 지금 자세 그대로 관절 제어 시작
            return
        self.sim = Lite3Sim()
        self.robot = Lite3SimInterface(self.sim)
        self.robot.Start()
        if viewer:
            import mujoco.viewer
            self.viewer = mujoco.viewer.launch_passive(self.sim.model, self.sim.data)
            self.viewer.cam.distance, self.viewer.cam.elevation = 2.0, -20
            atexit.register(self._keep_open)
        self._wall_start, self._sim_start = time.perf_counter(), self.sim.data.time
        self._hold(0.5)

    # ---------- 관절 하나 ----------
    def set_angle(self, leg, joint, deg):
        """관절 하나에 목표 각도를 준다(즉시). 모터는 그 각도를 향해 힘을 낸다."""
        q = self._targets()
        q[_index(leg, joint)] = np.radians(deg)
        self._send(q)

    def get_angle(self, leg, joint):
        """관절 하나의 현재 각도(센서 값)."""
        return float(np.degrees(self.robot.GetJointPosition()[_index(leg, joint)]))

    def set_stiffness(self, kp, kd=None):
        """모터 강성(kp)과 감쇠(kd). kp 가 클수록 목표 각도를 세게 지킨다. 기본 kp 120, kd 3."""
        self.kp = float(kp)
        if kd is not None:
            self.kd = float(kd)
        self._send(self._targets())

    # ---------- 여러 관절 ----------
    def get_angles(self):
        """{다리: (hip_x, hip_y, knee)} 현재 각도."""
        q = np.degrees(self.robot.GetJointPosition()).reshape(4, 3)
        return {leg: tuple(round(float(a), 1) for a in q[i]) for i, leg in enumerate(LEGS)}

    def move_to(self, pose, seconds=1.0):
        """여러 관절을 seconds 동안 부드럽게 목표 각도로 옮긴다(선형 보간).
        pose: "stand" 같은 이름, (hip_x, hip_y, knee) 하나(네 다리 공통), 또는 {다리: (…)}."""
        goal = self._pose_to_array(pose)
        if seconds <= 0:                       # 보간 없이 바로 목표 지정 (걸음새처럼 매 순간 직접 계산할 때)
            self._send(goal)
            return
        start = self._targets()
        n = max(1, int(seconds / 0.012))
        for i in range(1, n + 1):
            self._send(start + (goal - start) * i / n)
            self._advance(12)
        self._hold(0.2)

    def wait(self, seconds):
        self._hold(seconds)

    def reset(self):
        """처음 상태(엎드린 자세)로 되돌린다."""
        self.sim.reset()
        self.robot.Start()
        if not self._live:
            self._wall_start, self._sim_start = time.perf_counter(), self.sim.data.time
        self._hold(0.5)

    # ---------- 발 위치 ----------
    def get_foot(self, leg):
        """발끝 위치 (x, z) [m] — 정기구학."""
        _, hy, kn = self.get_angles()[leg]
        return forward_kinematics(hy, kn)

    def set_feet(self, feet, seconds=0.5):
        """발끝 위치 {다리: (x, z)} 로 이동 — 역기구학. seconds=0 이면 즉시."""
        q = np.degrees(self._targets()).reshape(4, 3)
        pose = {}
        for k, leg in enumerate(LEGS):
            hy, kn = inverse_kinematics(*feet[leg]) if leg in feet else q[k, 1:]
            pose[leg] = (q[k, 0], hy, kn)
        self.move_to(pose, seconds)

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

    # ---------- 몸 상태 ----------
    def get_height(self):
        return float(self.sim.base_pos[2])

    def get_tilt(self):
        r, p, _ = np.degrees(self.sim.rpy())
        return float(r), float(p)

    def get_position(self):
        x, y, _ = self.sim.base_pos
        return float(x), float(y)

    def get_heading(self):
        return float(np.degrees(self.sim.rpy()[2]))

    # ---------- 내부 ----------
    def _pose_to_array(self, pose):
        if isinstance(pose, str):
            pose = POSES[pose]
        if not isinstance(pose, dict):
            pose = {leg: pose for leg in LEGS}
        q = self._targets()
        for leg, angles in pose.items():
            i = LEGS.index(leg) * 3
            q[i:i + 3] = np.radians(angles)
        return q

    def _targets(self):
        """지금 내려가 있는 공식 관절 명령의 목표각(rad) 12개."""
        if self.sim.mode != "joint":
            self.robot.Start()
        return self.robot.GetJointCommand()[:, POS_COL].copy()

    def _send(self, q):
        """목표각(rad) 12개 → 공식 12×5 관절 명령으로 보낸다. 가동 범위 밖 값은 잘라낸다."""
        if self.sim.mode != "joint":
            self.robot.Start()
        q = np.clip(q, JOINT_LOWER, JOINT_UPPER)
        self.robot.SetJointCommand(make_joint_cmd(q, self.kp, self.kd))

    def _hold(self, seconds):
        self._advance(int(seconds / SIM_DT))

    def _advance(self, steps):
        if self._live:
            self._live.advance(steps)
            return
        for _ in range(steps):
            self.sim.step()
        if self.viewer:
            if not self.viewer.is_running():
                raise SystemExit("화면을 닫아서 프로그램을 종료합니다.")
            self.viewer.sync()
            lag = (self.sim.data.time - self._sim_start) - (time.perf_counter() - self._wall_start)
            if lag > 0:
                time.sleep(lag)

    def _keep_open(self):
        if not self.viewer.is_running():
            return
        print("프로그램 끝! 창을 닫으면 종료됩니다.")
        try:
            while True:
                self._advance(12)
        except SystemExit:
            pass
