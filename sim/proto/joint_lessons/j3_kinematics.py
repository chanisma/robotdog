"""3. 각도 ↔ 발 위치 — 정기구학과 역기구학.

다리 = 허벅지(0.20 m) + 정강이(0.21 m) 두 막대.
  정기구학: 각도를 알면 발 위치를 계산할 수 있다 (삼각함수)
  역기구학: 발을 놓고 싶은 위치에서 필요한 각도를 거꾸로 계산한다 (코사인 법칙)
"""
from _setup import JointDog, LEGS, forward_kinematics, inverse_kinematics, VIEW

print("서기 자세 각도 → 발 위치:", [round(v, 3) for v in forward_kinematics(-37.2, 74.5)])
print("발 위치 (0, -0.25) → 각도:", [round(v, 1) for v in inverse_kinematics(0.0, -0.25)])

dog = JointDog(viewer=VIEW)
dog.move_to("stand", 1.5)

# 팔굽혀펴기: 발끝 높이만 바꾸면 몸이 오르내린다
for z in [-0.22, -0.34, -0.22, -0.34]:
    dog.set_feet({leg: (0.02, z) for leg in LEGS}, seconds=0.8)
    print(f"발 높이 {z} m → 몸 높이 {dog.get_height():.2f} m")

# 인사하기: 앞발은 낮추고 뒷발은 높이면 몸이 앞으로 숙여진다
dog.set_feet({"FL": (0.02, -0.22), "FR": (0.02, -0.22), "HL": (0.02, -0.34), "HR": (0.02, -0.34)}, 1.0)
print("인사  pitch = %.1f°" % dog.get_tilt()[1])
dog.move_to("stand", 1.0)
