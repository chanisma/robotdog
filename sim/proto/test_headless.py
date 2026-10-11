"""화면 없이 걷기를 검증한다: 서기 → 전진 → 회전 → 횡이동 → 정지."""
import numpy as np

from lite3_sim import Lite3Sim, SIM_DT


def run(sim, seconds):
    for _ in range(int(seconds / SIM_DT)):
        sim.step()
        if sim.fallen():
            raise SystemExit(f"FAIL: 넘어짐 rpy(deg)={np.degrees(sim.rpy()).round(1)}")


sim = Lite3Sim()
sim.stand()
run(sim, 3.0)
print(f"서기     높이 {sim.base_pos[2]:.3f} m, mode={sim.mode}")

steps = [
    ("전진 0.5 m/s × 4 s", (0.5, 0.0, 0.0), 4.0),
    ("정지 × 1 s", (0.0, 0.0, 0.0), 1.0),
    ("좌회전 0.5 rad/s × 3 s", (0.0, 0.0, 0.5), 3.0),
    ("정지 × 1 s", (0.0, 0.0, 0.0), 1.0),
    ("왼쪽 횡이동 0.3 m/s × 3 s", (0.0, 0.3, 0.0), 3.0),
    ("정지 × 2 s", (0.0, 0.0, 0.0), 2.0),
]
for name, cmd, sec in steps:
    p0, yaw0 = sim.base_pos, sim.rpy()[2]
    sim.set_velocity(*cmd)
    run(sim, sec)
    d = sim.base_pos - p0
    c, s = np.cos(-yaw0), np.sin(-yaw0)
    fwd, side = c * d[0] - s * d[1], s * d[0] + c * d[1]
    dyaw = np.degrees((sim.rpy()[2] - yaw0 + np.pi) % (2 * np.pi) - np.pi)
    print(f"{name:26s} 전진 {fwd:+.2f} m, 옆 {side:+.2f} m, 회전 {dyaw:+6.1f}°, 높이 {sim.base_pos[2]:.3f} m")

print("PASS: 넘어지지 않고 모든 동작 완료")
