"""Lite3 3D 시뮬레이터 프로토타입 (Windows 지원, 순수 Python).

공식 Lite3_rl_deploy 의 MuJoCo 시뮬과 ONNX 정책 실행 로직을 그대로 옮긴 것이다.
  - 물리: MuJoCo 1 kHz (mujoco_simulation.py 의 DT = 0.001)
  - 정책: 12 스텝마다 실행 (lite3_test_policy_runner_onnx.cpp 의 decimation_ = 12)
  - 관측값 45개 = 각속도*0.25, 투영 중력, 속도명령, 관절위치-기본자세, 관절속도*0.05, 직전 행동
  - 행동 → 목표 관절각 = 기본자세 + 행동*스케일, PD 제어 (kp 30, kd 1)
관절 명령은 공식 RobotInterface::SetJointCommand 와 같은 12×5 행렬로 다룬다.
  열 = [kp, 목표각(rad), kd, 목표속도(rad/s), 보조토크(Nm)],  τ = kp·(목표각−q) + kd·(목표속도−dq) + 보조토크
"""
from pathlib import Path

import mujoco
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[2]
RL_DEPLOY = ROOT / "third_party" / "Lite3_rl_deploy"
MODEL_XML = RL_DEPLOY / "third_party/deep_robotics_model/Lite3/Lite3_mjcf/mjcf/Lite3.xml"
POLICY_ONNX = RL_DEPLOY / "policy/ppo/policy.onnx"

SIM_DT = 0.001
DECIMATION = 12

# lite3_test_policy_runner_onnx.cpp
DEFAULT_POS = np.array([0.0, -0.65, 1.30] * 4, dtype=np.float32)
ACTION_SCALE = np.array([0.125, 0.25, 0.25] * 4, dtype=np.float32)
KP, KD = 30.0, 1.0
MAX_CMD_VEL = np.array([0.8, 0.8, 0.8], dtype=np.float32)
OMEGA_SCALE, DOF_VEL_SCALE = 0.25, 0.05

# mujoco_simulation.py 의 엎드린 자세
LIE_POS = np.array([0.0, -1.35453, 2.54948] * 4, dtype=np.float32)
STANDUP_SEC = 1.5
STANDUP_KP, STANDUP_KD = 60.0, 2.0

# 관절 직접 제어 모드 (Lite3.xml 의 range, lite3_control_parameters.cpp 와 일치)
JOINT_KP, JOINT_KD = 120.0, 3.0   # 60 이면 몸이 처져 걸음새 실험에서 발이 끌림(측정)
JOINT_LOWER = np.array([-0.523, -2.67, 0.524] * 4, dtype=np.float32)
JOINT_UPPER = np.array([0.523, 0.314, 2.792] * 4, dtype=np.float32)

# 공식 관절 순서 (Lite3_rl_deploy robot_order)
JOINT_NAMES = [f"{leg}_{j}_joint" for leg in ("FL", "FR", "HL", "HR") for j in ("HipX", "HipY", "Knee")]
KP_COL, POS_COL, KD_COL, VEL_COL, TAU_COL = range(5)


def make_joint_cmd(pos, kp, kd, vel=0.0, tau=0.0):
    """12×5 관절 명령 행렬 [kp, 목표각, kd, 목표속도, 보조토크] 을 만든다."""
    cmd = np.zeros((12, 5), dtype=np.float32)
    cmd[:, KP_COL], cmd[:, POS_COL], cmd[:, KD_COL] = kp, pos, kd
    cmd[:, VEL_COL], cmd[:, TAU_COL] = vel, tau
    return cmd


# ---------- 짐(payload)과 무게중심 ----------
PAYLOAD_SIZE = (0.08, 0.06, 0.03)      # 짐 상자 반쪽 크기 (m) — 화면 표시용
PAYLOAD_Z = 0.075                      # 몸통 중심 위 높이 (m)
PAYLOAD_MAX = 5.0                      # kg (공식 연속 보행 하중: Pro 4 kg)
CONTACT_N = 5.0                        # 이 힘(N)보다 크게 눌리면 바닥에 닿은 발로 본다
FEET = ("FL", "FR", "HL", "HR")


def load_model():
    """공식 Lite3 MJCF 에 '짐' 바디(PAYLOAD)를 몸통 위에 덧붙인 모델. 짐이 없을 때는 0.1 g 이라 영향이 없다.
    기존 바디·관절 번호는 그대로이고 PAYLOAD 는 마지막 바디(18번)가 된다."""
    spec = mujoco.MjSpec.from_file(str(MODEL_XML))
    body = spec.body("TORSO").add_body(name="PAYLOAD", pos=[0, 0, PAYLOAD_Z])
    body.explicitinertial = True
    body.mass, body.inertia, body.ipos = 1e-4, [1e-7] * 3, [0, 0, 0]
    body.add_geom(name="PAYLOAD_visual", type=mujoco.mjtGeom.mjGEOM_BOX, size=list(PAYLOAD_SIZE),
                  group=2, contype=0, conaffinity=0, rgba=[1.0, 0.6, 0.2, 1.0])
    return spec.compile()


def _hull(pts):
    """2차원 점들의 볼록 껍질 (반시계 방향)."""
    pts = sorted(map(tuple, pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for q in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return lower[:-1] + upper[:-1]


def _seg_dist(p, a, b):
    ab, ap = b - a, p - a
    t = np.clip(ap @ ab / max(ab @ ab, 1e-12), 0, 1)
    return float(np.linalg.norm(ap - t * ab))


def stability_margin(com_xy, support):
    """무게중심 투영점이 지지 다각형 안쪽으로 얼마나 들어와 있는지 (m). 밖이면 음수.
    발이 2개뿐이면 선분이라 '정지 상태로는' 설 수 없다 → 선분까지 거리를 음수로.  발이 0~1개면 None."""
    if len(support) < 2:
        return None
    c = np.asarray(com_xy, float)
    poly = [np.asarray(q, float) for q in support]
    if len(poly) == 2:
        return -_seg_dist(c, poly[0], poly[1])
    dists, inside = [], True
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        e = b - a
        if e[0] * (c - a)[1] - e[1] * (c - a)[0] < 0:   # 반시계 다각형의 오른쪽 = 바깥
            inside = False
        dists.append(_seg_dist(c, a, b))
    d = min(dists)
    return d if inside else -d


class Lite3Sim:
    def __init__(self):
        self.model = load_model()
        self.payload_id = self.model.body("PAYLOAD").id
        self.payload = (0.0, 0.0, 0.0)               # (kg, x, y) 몸통 기준
        self.model.opt.timestep = SIM_DT
        self.data = mujoco.MjData(self.model)
        self.policy = ort.InferenceSession(str(POLICY_ONNX), providers=["CPUExecutionProvider"])
        self.reset()

    # ---------- 상태 ----------
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[2] = 0.12                      # 바닥에 엎드린 높이
        self.data.qpos[7:19] = LIE_POS
        mujoco.mj_forward(self.model, self.data)
        self.mode = "lie"                             # lie -> standup -> walk
        self.mode_time = 0.0
        self.cmd = np.zeros(3, dtype=np.float32)      # vx(m/s), vy(m/s), wz(rad/s)
        self.last_action = np.zeros(12, dtype=np.float32)
        self.joint_cmd = make_joint_cmd(LIE_POS, STANDUP_KP, STANDUP_KD)
        self.step_count = 0

    @property
    def joint_pos(self):
        return self.data.qpos[7:19].astype(np.float32)

    @property
    def joint_vel(self):
        return self.data.qvel[6:18].astype(np.float32)

    @property
    def base_pos(self):
        return self.data.qpos[0:3].copy()

    def rpy(self):
        w, x, y, z = self.data.qpos[3:7]
        roll = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
        pitch = np.arcsin(np.clip(2 * (w * y - z * x), -1, 1))
        yaw = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        return np.array([roll, pitch, yaw])

    # ---------- 명령 ----------
    def stand(self):
        self.mode, self.mode_time = "standup", 0.0
        self._standup_from = self.joint_pos.copy()

    def joint_mode(self, kp=JOINT_KP, kd=JOINT_KD):
        """관절 직접 제어 모드: 보행 정책을 끄고, 현재 자세를 PD로 유지한다.
        이후 관절 명령은 set_joint_command(12×5) 로 준다."""
        if self.mode != "joint":
            self.mode = "joint"
            self.joint_cmd = make_joint_cmd(self.joint_pos, kp, kd)

    def set_joint_command(self, cmd):
        cmd = np.asarray(cmd, dtype=np.float32)
        if cmd.shape != (12, 5):
            raise ValueError(f"관절 명령은 12×5 행렬이어야 해요 (받은 크기: {cmd.shape})")
        self.joint_cmd = cmd.copy()

    @property
    def joint_torque(self):
        return self.data.actuator_force.astype(np.float32)

    def set_velocity(self, vx=0.0, vy=0.0, wz=0.0):
        self.cmd = np.clip(np.array([vx, vy, wz], dtype=np.float32), -MAX_CMD_VEL, MAX_CMD_VEL)

    # ---------- 제어 ----------
    def _observation(self):
        omega = self.data.qvel[3:6].astype(np.float32) * OMEGA_SCALE   # 몸체 좌표계 각속도
        rot = np.zeros(9)
        mujoco.mju_quat2Mat(rot, self.data.qpos[3:7])
        projected_gravity = rot.reshape(3, 3).T @ np.array([0.0, 0.0, -1.0])
        return np.concatenate([
            omega,
            projected_gravity.astype(np.float32),
            self.cmd,
            self.joint_pos - DEFAULT_POS,
            self.joint_vel * DOF_VEL_SCALE,
            self.last_action,
        ]).astype(np.float32)[None, :]

    def _update_target(self):
        if self.mode == "standup":
            a = min(self.mode_time / STANDUP_SEC, 1.0)
            self.joint_cmd = make_joint_cmd((1 - a) * self._standup_from + a * DEFAULT_POS,
                                            STANDUP_KP, STANDUP_KD)
            if a >= 1.0:
                self.mode, self.mode_time = "walk", 0.0
                self.last_action[:] = 0
        elif self.mode == "walk" and self.step_count % DECIMATION == 0:
            action = self.policy.run(["actions"], {"obs": self._observation()})[0][0]
            self.last_action = action.astype(np.float32)
            self.joint_cmd = make_joint_cmd(DEFAULT_POS + self.last_action * ACTION_SCALE, KP, KD)

    def step(self):
        self._update_target()
        c = self.joint_cmd
        tau = (c[:, KP_COL] * (c[:, POS_COL] - self.joint_pos)
               + c[:, KD_COL] * (c[:, VEL_COL] - self.joint_vel) + c[:, TAU_COL])
        self.data.ctrl[:] = tau                     # MJCF ctrlrange ±30 Nm 로 잘림
        mujoco.mj_step(self.model, self.data)
        self.step_count += 1
        self.mode_time += SIM_DT

    # ---------- 짐과 무게중심 ----------
    def set_payload(self, kg, x=0.0, y=0.0):
        """몸통 위에 kg 짜리 짐을 올린다. x: 앞(+)/뒤(−), y: 왼쪽(+)/오른쪽(−) [m, 몸통 중심 기준]. 시뮬레이터 전용."""
        kg = float(np.clip(kg, 0.0, PAYLOAD_MAX))
        x, y = float(np.clip(x, -0.25, 0.25)), float(np.clip(y, -0.15, 0.15))
        m, i = self.model, self.payload_id
        m.body_mass[i] = max(kg, 1e-4)
        sx, sy, sz = (2 * v for v in PAYLOAD_SIZE)
        m.body_inertia[i] = max(kg, 1e-4) / 12 * np.array([sy**2 + sz**2, sx**2 + sz**2, sx**2 + sy**2])
        m.body_pos[i] = [x, y, PAYLOAD_Z]
        m.body_ipos[i] = 0
        # 무게중심 계산(subtree_com)이 쓰는 '부분 트리 질량' 상수도 다시 계산 (mj_setConst 는 자세를 건드려서 쓰지 않음)
        m.body_subtreemass[:] = m.body_mass
        for b in range(m.nbody - 1, 0, -1):
            m.body_subtreemass[m.body_parentid[b]] += m.body_subtreemass[b]
        mujoco.mj_forward(m, self.data)
        self.payload = (kg, x, y)

    def com(self):
        """로봇 전체(짐 포함)의 무게중심 (세계 좌표, m)."""
        return self.data.subtree_com[1].copy()

    def feet_world(self):
        return np.array([self.data.xpos[self.model.body(f"{leg}_FOOT").id] for leg in FEET])

    def contacts(self):
        """발마다 바닥에 닿아 있는지 (정강이 끝 포함, 눌리는 힘 > CONTACT_N)."""
        m, d = self.model, self.data
        legs = {m.body(f"{leg}_{part}").id: k for k, leg in enumerate(FEET) for part in ("SHANK", "FOOT")}
        fz = np.zeros(4)
        f6 = np.zeros(6)
        for i in range(d.ncon):
            con = d.contact[i]
            b1, b2 = m.geom_bodyid[con.geom1], m.geom_bodyid[con.geom2]
            for body in (b1, b2):
                if body in legs:
                    mujoco.mj_contactForce(m, d, i, f6)
                    fz[legs[body]] += abs((con.frame.reshape(3, 3).T @ f6[:3])[2])
        return fz > CONTACT_N

    def support_info(self):
        """무게중심, 바닥 접촉 발, 지지 다각형(세계 xy), 여유(m)."""
        com = self.com()
        feet = self.feet_world()
        touch = self.contacts()
        support = _hull(feet[touch, :2]) if touch.sum() >= 2 else [tuple(p) for p in feet[touch, :2]]
        return {"com": com, "feet": feet, "contact": touch, "support": support,
                "margin": stability_margin(com[:2], support)}

    def fallen(self):
        r, p, _ = self.rpy()
        return abs(r) > np.radians(30) or abs(p) > np.radians(45)   # rl_control_state 기준
