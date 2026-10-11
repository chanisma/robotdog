"""5. 걸음새 직접 만들기 — 트롯(trot): 대각선 두 다리씩 번갈아 딛기.

한 다리의 한 주기(T초) = 딛기(stance, 발을 뒤로 밀기) + 옮기기(swing, 발을 들어 앞으로)
FL·HR 이 딛는 동안 FR·HL 은 옮기고, 반 주기 뒤에 서로 바꾼다.
"""
import math

from _setup import JointDog, VIEW

T = 0.4          # 한 주기 시간 (초)
STEP = 0.08      # 보폭 (m)
LIFT = 0.08      # 발 드는 높이 (m)
HEIGHT = -0.31   # 딛는 발의 높이 (m)
PHASE = {"FL": 0.0, "HR": 0.0, "FR": 0.5, "HL": 0.5}   # 대각선 짝


def foot_at(p):
    """주기 안의 위치 p(0~1) → 발끝 (x, z)"""
    if p < 0.5:                                 # 딛기: 앞(+STEP/2) → 뒤(-STEP/2)
        return STEP / 2 - STEP * (p / 0.5), HEIGHT
    s = (p - 0.5) / 0.5                         # 옮기기: 뒤 → 앞, 반원 모양으로 들어 올림
    return -STEP / 2 + STEP * s, HEIGHT + LIFT * math.sin(math.pi * s)


dog = JointDog(viewer=VIEW)
dog.move_to("stand", 1.5)
start = dog.get_position()

t = 0.0
while t < 10 * T:                               # 10 주기
    feet = {}
    for leg, phase in PHASE.items():
        x, z = foot_at((t / T + phase) % 1.0)
        feet[leg] = (x + 0.02, z)
    dog.set_feet(feet, seconds=0)               # 매 순간 목표 위치 지정
    dog.wait(0.012)
    t += 0.012

x0, y0 = start
x1, y1 = dog.get_position()
print(f"10 주기 동안 이동: {x1 - x0:+.2f} m (이론값 {10 * STEP:.2f} m)")

# 실험: dog.move_to("stand", 1.5) 다음 줄에 dog.set_stiffness(60) 을 넣어 모터 강성을 낮춰 보자. 왜 뒤로 갈까?
# 도전: 오른쪽 다리 보폭만 크게 하면? → 회전!
