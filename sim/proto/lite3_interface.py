"""DEEP Robotics 공식 로봇 인터페이스의 시뮬레이터 구현.

공식 C++ 인터페이스(Lite3_rl_deploy/interface/robot/robot_interface.h, interface::RobotInterface)와
함수 이름·단위·자료 형식을 똑같이 맞췄다. 실물에서는 같은 함수를 hardware_interface 가 구현한다.

  관절 순서 (12개): FL_HipX, FL_HipY, FL_Knee, FR_…, HL_…, HR_…   (JOINT_NAMES)
  단위: 각도 rad, 각속도 rad/s, 토크 Nm, 가속도 m/s²
  SetJointCommand(cmd): cmd 는 12×5 행렬, 각 열 = [kp, 목표각, kd, 목표속도, 보조토크]
                         모터 토크 τ = kp·(목표각−현재각) + kd·(목표속도−현재속도) + 보조토크

시간 진행: 실물은 실제 시간이 흐르지만, 시뮬에서는 이 인터페이스를 가진 쪽(JointDog 등)이 시뮬을 진행시킨다.
"""
import mujoco
import numpy as np

from lite3_sim import JOINT_NAMES, SIM_DT  # noqa: F401  (JOINT_NAMES 는 다시 내보냄)

ACC_ADR, GYRO_ADR = 16, 19          # Lite3.xml 의 accelerometer, gyro 센서 위치 (mujoco_simulation.py 와 동일)


class Lite3SimInterface:
    """interface::RobotInterface 의 시뮬레이터 버전."""

    def __init__(self, sim):
        self.sim = sim
        self.robot_name_ = "Lite3"
        self.dof_num_ = 12

    def Start(self):
        """관절 명령을 받기 시작한다: 보행 정책을 끄고 지금 자세를 유지."""
        self.sim.joint_mode()

    def Stop(self):
        pass

    def GetInterfaceTimeStamp(self):
        return float(self.sim.data.time)

    def GetJointPosition(self):
        return self.sim.joint_pos.copy()

    def GetJointVelocity(self):
        return self.sim.joint_vel.copy()

    def GetJointTorque(self):
        return self.sim.joint_torque.copy()

    def GetImuRpy(self):
        return self.sim.rpy().astype(np.float32)

    def GetImuAcc(self):
        return self.sim.data.sensordata[ACC_ADR:ACC_ADR + 3].astype(np.float32)

    def GetImuOmega(self):
        return self.sim.data.sensordata[GYRO_ADR:GYRO_ADR + 3].astype(np.float32)

    def SetJointCommand(self, cmd):
        self.sim.set_joint_command(cmd)

    def GetJointCommand(self):
        return self.sim.joint_cmd.copy()

    def GetContactForce(self):
        """발 4개(FL, FR, HL, HR)의 접촉력 [Fx, Fy, Fz] × 4 = 12개 (세계 좌표계, N)."""
        m, d = self.sim.model, self.sim.data
        # Lite3.xml 에서는 정강이(SHANK) 충돌 메시 끝부분이 바닥에 닿는다 → 정강이·발 바디를 그 다리의 발로 본다
        legs = {m.body(f"{leg}_{part}").id: k for k, leg in enumerate(("FL", "FR", "HL", "HR"))
                for part in ("SHANK", "FOOT")}
        force = np.zeros((4, 3))
        f6 = np.zeros(6)
        for i in range(d.ncon):
            con = d.contact[i]
            b1, b2 = m.geom_bodyid[con.geom1], m.geom_bodyid[con.geom2]
            for body in (b1, b2):
                if body in legs:
                    mujoco.mj_contactForce(m, d, i, f6)
                    f_world = con.frame.reshape(3, 3).T @ f6[:3]   # geom1 이 geom2 에 주는 힘
                    force[legs[body]] += f_world if body == b2 else -f_world   # 다리가 받는 힘 (지지하면 Fz > 0)
        return force.reshape(-1).astype(np.float32)
