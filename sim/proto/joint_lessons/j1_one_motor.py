"""1. 모터 하나 움직이기 — 목표 각도를 주면 모터가 그 각도로 간다.

로봇은 엎드린 상태에서 시작한다. 앞왼쪽(FL) 다리의 관절 3개를 하나씩 움직여 보자.
"""
from _setup import JointDog, VIEW

dog = JointDog(viewer=VIEW)
dog.reset()       # 엎드린 처음 자세에서 시작 (지우면 지금 자세에서 이어서 시작)

for joint, goal in [("hip_x", 25), ("hip_y", -30), ("knee", 100)]:
    before = dog.get_angle("FL", joint)
    dog.set_angle("FL", joint, goal)       # 목표 각도 주기 (공식 관절 명령의 '목표각')
    dog.wait(0.6)
    after = dog.get_angle("FL", joint)     # 현재 각도 읽기 (공식 GetJointPosition)
    print(f"FL {joint:5s}: {before:7.1f}° → 목표 {goal}° → 실제 {after:7.1f}°")

# 생각해 보기: 목표와 실제 각도가 조금 다른 이유는? (중력, 모터 강성)
# 도전: 가동 범위 밖의 값(예: knee 200°)을 주면 어떻게 될까?
