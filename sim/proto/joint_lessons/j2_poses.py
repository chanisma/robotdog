"""2. 자세 = 관절 12개 각도의 묶음 — 엎드리기, 서기, 앉기."""
from _setup import JointDog, VIEW

dog = JointDog(viewer=VIEW)
dog.reset()       # 엎드린 처음 자세에서 시작 (지우면 지금 자세에서 이어서 시작)
print("엎드린 자세:", dog.get_angles())

dog.move_to("stand", seconds=1.5)          # 1.5초 동안 부드럽게
print("서기  높이 %.2f m" % dog.get_height())

# 강아지처럼 앉기: 앞다리는 펴고, 뒷다리는 접는다 (다리마다 (hip_x, hip_y, knee))
sit = {"FL": (0, -25, 50), "FR": (0, -25, 50), "HL": (0, -95, 150), "HR": (0, -95, 150)}
dog.move_to(sit, seconds=1.5)
print("앉기  기울기(roll, pitch) =", [round(a, 1) for a in dog.get_tilt()])

dog.move_to("stand", seconds=1.5)
dog.move_to("lie", seconds=0.1)            # 너무 빨리 움직이면?
print("0.1초 만에 엎드리기 → 높이 %.2f m (쾅!)" % dog.get_height())

# 생각해 보기: seconds 를 0.1 로 하면 실제 로봇에는 어떤 일이 생길까?
