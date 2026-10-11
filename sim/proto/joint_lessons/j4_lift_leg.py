"""4. 다리 하나 들기 — 무게중심과 지지 다각형.

다리를 하나 들면 남은 세 발이 만드는 삼각형(지지 다각형) 안에 무게중심이 있어야 넘어지지 않는다.
3D 화면의 노란 점이 무게중심, 바닥의 초록/빨강 영역이 지지 다각형이다.
dog.get_com_margin() 은 무게중심이 지지 다각형 안쪽으로 몇 cm 들어와 있는지 알려 준다 (음수 = 밖).
"""
from _setup import JointDog, LEGS, inverse_kinematics, VIEW

LIFT_FL = {"FL": (0, -80, 140)}            # 앞왼쪽 다리를 접어 올린 자세 (hip_x, hip_y, knee)

# 실험 A: 그냥 든다
dog = JointDog(viewer=VIEW)
dog.move_to("stand", 1.5)
print("A. 네 발로 섰을 때 여유:", dog.get_com_margin(), "cm")
dog.move_to(LIFT_FL, 0.6)
print("A. 다리를 든 순간 여유:", dog.get_com_margin(), "cm")
dog.wait(1.0)
print("A. 그냥 들기          roll %.1f°  ← 넘어짐!" % dog.get_tilt()[0])

# 실험 B: 무게중심을 뒤로 옮긴 다음 든다
dog.reset()
dog.move_to("stand", 1.5)
hip_y, knee = inverse_kinematics(0.07, -0.31)           # 네 발을 몸 기준 7 cm 앞으로 → 몸이 약 9 cm 뒤로 감
dog.move_to({leg: (0, hip_y, knee) for leg in LEGS}, 1.0)
dog.move_to(LIFT_FL, 0.6)
dog.wait(1.0)
print("B. 다리를 든 뒤 여유:", dog.get_com_margin(), "cm")
print("B. 무게중심 뒤로 옮기고 들기 roll %.1f°  ← 버팀!" % dog.get_tilt()[0])

# 생각해 보기: 앞왼쪽 다리를 들면 남는 발은 앞오른쪽·뒤왼쪽·뒤오른쪽.
#   조작 패널 ④ 무게중심 탭을 열고, 위에서 본 그림에서 노란 점이 삼각형 안에 있는지 확인해 보자.
# 도전: 7 cm 대신 2 cm, 4 cm 로 바꿔 보자. 몇 cm 부터 버틸까? 여유(cm)가 어떻게 달라질까?
# 도전: dog.set_payload(3, x=0.15) 로 앞쪽에 짐을 올리면 실험 B 가 어떻게 될까?
