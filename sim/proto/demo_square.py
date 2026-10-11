"""학생 코드 예시: 1 m 정사각형 걷기 (9차시).

실행: python demo_square.py            (3D 화면)
      python demo_square.py --no-view  (화면 없이 결과만)
"""
import sys

from lite3_edu_proto import Robot

dog = Robot("mock", viewer="--no-view" not in sys.argv)

dog.stand()
for i in range(4):
    dog.forward(1.0)
    dog.turn_left(90)
dog.sit()

x, y = dog.get_position()
print(f"도착 위치: x={x:.2f} m, y={y:.2f} m, 방향={dog.get_heading():.1f}°")
