"""조작 패널 — 슬라이더와 그림으로 값을 바꾸며 3D 로봇이 어떻게 움직이는지 눈으로 확인한다.

코드 스튜디오(studio.py)에서 연다. 패널은 켜져 있는 시뮬레이터(sim_server.py)에 명령을 보내고,
시뮬레이터가 10 Hz 로 보내는 상태(state)를 받아 그림과 숫자를 갱신한다.
바꾼 값은 항상 "코드로 쓰면 이렇게" 와 "딥 로보틱스 공식 형식" 으로 함께 보여 준다.
"""
import math
import tkinter as tk
from tkinter import ttk

from lite3_joint_proto import (JOINT_INFO, JOINT_RANGE_DEG, LEG_NAMES, LEGS, POSES, SHANK, THIGH,
                               forward_kinematics, inverse_kinematics, official_name, trot_feet)

JOINTS = ["hip_x", "hip_y", "knee"]
UI = ("Malgun Gothic", 10)
UI_BOLD = ("Malgun Gothic", 10, "bold")
SMALL = ("Malgun Gothic", 9)
MONO = ("Consolas", 11)
THIGH_C, SHANK_C, TARGET_C, GRID_C = "#2f6fdf", "#e07b00", "#bbbbbb", "#e6e6e6"
SEND_EVERY_MS = 50


def pose_degrees(name):
    pose = POSES[name]
    pose = pose if isinstance(pose, dict) else {leg: pose for leg in LEGS}
    return [float(a) for leg in LEGS for a in pose[leg]]


class LegView:
    """옆에서 본 다리 그림 (엉덩이 관절 기준, cm 눈금). 발을 끌어 옮길 수도 있다."""

    def __init__(self, parent, width=300, height=300, scale=600, on_drag=None):
        self.c = tk.Canvas(parent, width=width, height=height, background="white", highlightthickness=1,
                           highlightbackground="#ccc")
        self.w, self.h, self.s = width, height, scale            # scale: 1 m = s px
        self.ox, self.oy = width / 2, 34                          # 엉덩이 관절 위치
        self.on_drag = on_drag
        if on_drag:
            self.c.bind("<Button-1>", self._drag)
            self.c.bind("<B1-Motion>", self._drag)

    def to_px(self, x, z):
        return self.ox + x * self.s, self.oy - z * self.s

    def to_m(self, px, py):
        return (px - self.ox) / self.s, (self.oy - py) / self.s

    def _drag(self, e):
        self.on_drag(*self.to_m(e.x, e.y))

    def _grid(self):
        c = self.c
        for cm in range(-30, 31, 10):
            x, _ = self.to_px(cm / 100, 0)
            c.create_line(x, 0, x, self.h, fill=GRID_C)
            c.create_text(x, self.h - 8, text=f"{cm}", font=("Malgun Gothic", 7), fill="#999")
        for cm in range(0, 46, 10):
            _, y = self.to_px(0, -cm / 100)
            c.create_line(0, y, self.w, y, fill=GRID_C)
            c.create_text(12, y, text=f"-{cm}" if cm else "0", font=("Malgun Gothic", 7), fill="#999")
        c.create_text(self.w - 6, self.h - 22, text="앞 →  (cm)", anchor="e", font=SMALL, fill="#777")
        c.create_text(22, self.h - 24, text="옆에서 본 모습", anchor="w", font=SMALL, fill="#777")
        c.create_rectangle(self.ox - 70, self.oy - 22, self.ox + 70, self.oy - 6, fill="#d9d9d9", outline="#aaa")
        c.create_text(self.ox, self.oy - 14, text="몸통", font=("Malgun Gothic", 8), fill="#555")

    def _leg(self, hip_y, knee, colors, width, dash=None):
        q1, q2 = math.radians(hip_y), math.radians(knee)
        kx, kz = THIGH * math.sin(q1), -THIGH * math.cos(q1)
        fx, fz = forward_kinematics(hip_y, knee)
        hx, hy = self.to_px(0, 0)
        k = self.to_px(kx, kz)
        f = self.to_px(fx, fz)
        self.c.create_line(hx, hy, *k, fill=colors[0], width=width, dash=dash, capstyle="round")
        self.c.create_line(*k, *f, fill=colors[1], width=width, dash=dash, capstyle="round")
        return k, f, (fx, fz)

    def draw(self, actual, target=None, reach=False, label_angles=True):
        """actual / target: (hip_y, knee) 도."""
        c = self.c
        c.delete("all")
        self._grid()
        if reach:
            r = (THIGH + SHANK) * self.s
            c.create_oval(self.ox - r, self.oy - r, self.ox + r, self.oy + r, outline="#f3b5b5", dash=(3, 3))
            c.create_text(self.ox + r * 0.72, self.oy + r * 0.72, text="다리가 닿는 한계", font=("Malgun Gothic", 7),
                          fill="#d77")
        if target:
            self._leg(*target, (TARGET_C, TARGET_C), 3, dash=(4, 3))
        k, f, (fx, fz) = self._leg(*actual, (THIGH_C, SHANK_C), 7)
        c.create_oval(self.ox - 6, self.oy - 6, self.ox + 6, self.oy + 6, fill="#333")
        c.create_oval(k[0] - 5, k[1] - 5, k[0] + 5, k[1] + 5, fill="#333")
        c.create_oval(f[0] - 7, f[1] - 7, f[0] + 7, f[1] + 7, fill="#c33", outline="")
        if label_angles:
            c.create_text(self.ox + 10, self.oy + 14, text=f"hip_y {actual[0]:.0f}°", anchor="w", font=SMALL,
                          fill=THIGH_C)
            c.create_text(k[0] + 10, k[1], text=f"knee {actual[1]:.0f}°", anchor="w", font=SMALL, fill=SHANK_C)
        c.create_text(f[0] + 10, f[1] + 12, text=f"발 ({fx * 100:.0f}, {fz * 100:.0f}) cm", anchor="w", font=SMALL,
                      fill="#c33")


class FrontView:
    """뒤에서 본 다리 그림 — hip_x (옆으로 벌리기) 확인용. 화면 오른쪽 = 로봇의 오른쪽."""

    def __init__(self, parent, width=170, height=300):
        self.c = tk.Canvas(parent, width=width, height=height, background="white", highlightthickness=1,
                           highlightbackground="#ccc")
        self.w, self.h = width, height

    def draw(self, hip_x, target=None, length=0.30):
        c, s = self.c, 600
        c.delete("all")
        ox, oy = self.w / 2, 34
        c.create_text(ox, self.h - 34, text="뒤에서 본 모습", font=SMALL, fill="#777")
        c.create_rectangle(ox - 60, oy - 22, ox + 60, oy - 6, fill="#d9d9d9", outline="#aaa")
        c.create_text(ox - 40, oy - 14, text="왼쪽", font=("Malgun Gothic", 7), fill="#777")
        c.create_text(ox + 40, oy - 14, text="오른쪽", font=("Malgun Gothic", 7), fill="#777")
        c.create_line(ox, 0, ox, self.h, fill=GRID_C)
        for ang, col, w, dash in ([(target, TARGET_C, 3, (4, 3))] if target is not None else []) + \
                [(hip_x, "#6a3fbf", 7, None)]:
            a = math.radians(ang)
            fx, fy = ox + math.sin(a) * length * s, oy + math.cos(a) * length * s
            c.create_line(ox, oy, fx, fy, fill=col, width=w, dash=dash, capstyle="round")
        a = math.radians(hip_x)
        fx, fy = ox + math.sin(a) * length * s, oy + math.cos(a) * length * s
        c.create_oval(ox - 6, oy - 6, ox + 6, oy + 6, fill="#333")
        c.create_oval(fx - 7, fy - 7, fx + 7, fy + 7, fill="#c33", outline="")
        c.create_text(ox, self.h - 14, text=f"hip_x {hip_x:.0f}°", font=SMALL, fill="#6a3fbf")


class ControlPanel:
    def __init__(self, studio):
        self.studio = studio
        self.win = tk.Toplevel(studio.root)
        self.win.title("조작 패널 — 값을 바꾸며 로봇 움직임 보기")
        self.win.geometry("680x900")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.state = None
        self.goal = None                  # 패널이 보내는 목표각(도) 12개. None 이면 다음 상태에서 맞춤
        self._updating = False
        self._send_job = None
        self._pending = None

        self._build_status()
        self._build_code_box()                 # 창 아래쪽에 고정
        self.nb = ttk.Notebook(self.win)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._build_joint_tab()
        self._build_foot_tab()
        self._build_gait_tab()
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._refresh_code())
        self._refresh_code()

    # ================= 공통: 상태 표시 =================
    def _build_status(self):
        top = ttk.LabelFrame(self.win, text="로봇 상태 (시뮬레이터에서 실시간으로 읽음)", padding=6)
        top.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(top)
        row.pack(fill="x")
        self.status_lbl = ttk.Label(row, text="시뮬레이터 연결 중…", font=UI)
        self.status_lbl.pack(side="left")
        row2 = ttk.Frame(top)
        row2.pack(fill="x", pady=(6, 0))
        self.force_cv = tk.Canvas(row2, width=236, height=52, background="white", highlightthickness=0)
        self.force_cv.pack(side="right")
        ttk.Label(row2, text="자세:", font=UI).pack(side="left")
        for name, label in [("lie", "엎드리기"), ("stand", "서기"), ("sit", "앉기")]:
            ttk.Button(row2, text=label, command=lambda n=name: self.pose(n)).pack(side="left", padx=2)
        ttk.Button(row2, text="↺ 처음 자세", command=self.studio.reset_robot).pack(side="left", padx=(8, 0))

        row3 = ttk.Frame(top)
        row3.pack(fill="x", pady=(6, 0))
        ttk.Label(row3, text="모터 힘(강성) kp", font=UI).pack(side="left")
        self.kp_var = tk.DoubleVar(value=120)
        ttk.Scale(row3, from_=20, to=250, variable=self.kp_var, length=220,
                  command=lambda v: self._on_kp()).pack(side="left", padx=6)
        self.kp_lbl = ttk.Label(row3, text="120", width=5, font=UI_BOLD)
        self.kp_lbl.pack(side="left")
        ttk.Label(top, text="kp: 모터가 목표 각도를 얼마나 세게 지키는지. 낮추면 몸무게에 눌려 무릎이 굽고 몸이 내려가요.",
                  font=SMALL, foreground="#666").pack(anchor="w", pady=(2, 0))

    def _draw_forces(self, fz):
        c = self.force_cv
        c.delete("all")
        c.create_text(2, 7, text="발이 받는 무게 (kg)", anchor="w", font=("Malgun Gothic", 8), fill="#555")
        for i, leg in enumerate(LEGS):
            kg = max(0.0, fz[i] / 9.81)
            x = 4 + i * 58
            h = min(24, kg * 3)
            c.create_rectangle(x, 40 - h, x + 16, 40, fill="#7aa6e8" if kg > 0.2 else "#eee", outline="")
            c.create_text(x + 8, 47, text=leg, font=("Malgun Gothic", 7), fill="#555")
            c.create_text(x + 20, 34, text=f"{kg:.1f}", anchor="w", font=("Malgun Gothic", 8))

    # ================= ① 관절 하나씩 =================
    def _build_joint_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text="① 관절 하나씩")
        row = ttk.Frame(tab)
        row.pack(fill="x")
        ttk.Label(row, text="다리:", font=UI).pack(side="left")
        self.leg_var = tk.StringVar(value="FL")
        for leg in LEGS:
            ttk.Radiobutton(row, text=f"{LEG_NAMES[leg]} ({leg})", value=leg, variable=self.leg_var,
                            command=self._on_leg_change).pack(side="left", padx=3)
        self.all_legs = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab, text="네 다리 똑같이 움직이기", variable=self.all_legs).pack(anchor="w", pady=(2, 4))

        self.sliders, self.val_lbls = {}, {}
        for j in JOINTS:
            name, meaning = JOINT_INFO[j]
            box = ttk.Frame(tab)
            box.pack(fill="x", pady=2)
            head = ttk.Frame(box)
            head.pack(fill="x")
            ttk.Label(head, text=f"{name}  ({j})", font=UI_BOLD, width=22).pack(side="left")
            lo, hi = JOINT_RANGE_DEG[j]
            var = tk.DoubleVar(value=0)
            ttk.Scale(head, from_=lo, to=hi, variable=var, length=230,
                      command=lambda v, j=j: self._on_joint_slider(j)).pack(side="left", padx=4)
            lbl = ttk.Label(head, text="", width=20, font=SMALL)
            lbl.pack(side="left")
            ttk.Label(box, text=f"{meaning}   (범위 {lo:.0f}° ~ {hi:.0f}°)", font=SMALL, foreground="#666").pack(anchor="w")
            self.sliders[j], self.val_lbls[j] = var, lbl

        views = ttk.Frame(tab)
        views.pack(pady=6)
        self.side_view = LegView(views, width=300, height=262)
        self.side_view.c.pack(side="left")
        self.front_view = FrontView(views, height=262)
        self.front_view.c.pack(side="left", padx=6)
        ttk.Label(tab, text="굵은 선 = 실제 다리,  회색 점선 = 목표.  파랑 = 허벅지, 주황 = 정강이, 빨간 점 = 발끝",
                  font=SMALL, foreground="#666").pack()
        self.last_joint = "knee"

    def _on_leg_change(self):
        self._sync_sliders()
        self._refresh_code()

    def _on_joint_slider(self, joint):
        if self._updating or self.goal is None:
            return
        deg = round(self.sliders[joint].get())
        legs = LEGS if self.all_legs.get() else [self.leg_var.get()]
        for leg in legs:
            self.goal[LEGS.index(leg) * 3 + JOINTS.index(joint)] = deg
        self.last_joint = joint
        self._queue({"op": "joints", "deg": list(self.goal)})
        self._refresh_code()

    def _sync_sliders(self):
        if self.goal is None:
            return
        self._updating = True
        i = LEGS.index(self.leg_var.get()) * 3
        for k, j in enumerate(JOINTS):
            self.sliders[j].set(self.goal[i + k])
        self._updating = False

    # ================= ② 발 위치로 =================
    def _build_foot_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text="② 발 위치로 (역기구학)")
        ttk.Label(tab, text="그림에서 빨간 발끝을 마우스로 끌거나 슬라이더를 움직여 보세요.\n"
                            "컴퓨터가 그 위치에 발을 놓기 위한 hip_y 와 knee 각도를 거꾸로 계산해요 (역기구학).",
                  font=SMALL, foreground="#444").pack(anchor="w")
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="움직일 발:", font=UI).pack(side="left")
        self.foot_target = tk.StringVar(value="all")
        ttk.Radiobutton(row, text="네 발 모두", value="all", variable=self.foot_target,
                        command=self._refresh_code).pack(side="left", padx=3)
        for leg in LEGS:
            ttk.Radiobutton(row, text=LEG_NAMES[leg], value=leg, variable=self.foot_target,
                            command=self._refresh_code).pack(side="left", padx=3)

        self.foot_x = tk.DoubleVar(value=2)
        self.foot_z = tk.DoubleVar(value=31)
        for text, var, lo, hi, note in [
                ("앞뒤 x (cm)", self.foot_x, -20, 20, "+ 앞 / − 뒤"),
                ("엉덩이 아래 깊이 (cm)", self.foot_z, 12, 40, "클수록 몸이 높아짐")]:
            r = ttk.Frame(tab)
            r.pack(fill="x", pady=2)
            ttk.Label(r, text=text, font=UI_BOLD, width=20).pack(side="left")
            ttk.Scale(r, from_=lo, to=hi, variable=var, length=240,
                      command=lambda v: self._on_foot_slider()).pack(side="left", padx=4)
            ttk.Label(r, textvariable=var, width=4).pack(side="left")
            ttk.Label(r, text=note, font=SMALL, foreground="#666").pack(side="left", padx=4)

        self.ik_lbl = ttk.Label(tab, text="", font=UI_BOLD)
        self.ik_lbl.pack(anchor="w", pady=(4, 2))
        self.foot_view = LegView(tab, width=420, height=330, scale=700, on_drag=self._on_foot_drag)
        self.foot_view.c.pack(pady=4)
        self._draw_foot_view()

    def _on_foot_drag(self, x, z):
        self.foot_x.set(round(x * 100))
        self.foot_z.set(round(-z * 100))
        self._on_foot_slider()

    def _foot_xz(self):
        return round(self.foot_x.get()) / 100, -round(self.foot_z.get()) / 100

    def _on_foot_slider(self):
        if self._updating:
            return
        x, z = self._foot_xz()
        self._draw_foot_view()
        self._refresh_code()
        try:
            hy, kn = inverse_kinematics(x, z)
        except ValueError:
            return
        if self.goal is None:
            return
        legs = LEGS if self.foot_target.get() == "all" else [self.foot_target.get()]
        for leg in legs:
            i = LEGS.index(leg) * 3
            self.goal[i + 1], self.goal[i + 2] = round(hy, 1), round(kn, 1)
        self._queue({"op": "joints", "deg": list(self.goal)})

    def _draw_foot_view(self):
        x, z = self._foot_xz()
        try:
            hy, kn = inverse_kinematics(x, z)
            self.foot_view.draw((hy, kn), reach=True)
            self.ik_lbl.configure(text=f"→ 계산된 각도:  hip_y = {hy:.1f}°,   knee = {kn:.1f}°", foreground="#222")
        except ValueError:
            self.foot_view.draw((-37.2, 74.5), reach=True)
            self.ik_lbl.configure(text="✖ 다리가 닿을 수 없는 위치예요 (허벅지 20 cm + 정강이 21 cm = 최대 41 cm)",
                                  foreground="#c33")

    # ================= ③ 걸음새 =================
    def _build_gait_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text="③ 걸음새 (트롯)")
        ttk.Label(tab, text="트롯: 대각선 두 다리(앞왼쪽+뒤오른쪽, 앞오른쪽+뒤왼쪽)가 번갈아 딛고 옮겨요.\n"
                            "한 주기 = 딛기(발을 뒤로 밀기, 갈색) + 옮기기(발을 들어 앞으로, 초록).",
                  font=SMALL, foreground="#444").pack(anchor="w")
        self.g = {}
        for key, text, lo, hi, init, note in [
                ("T", "한 주기 시간 T (초)", 0.25, 0.8, 0.4, "짧을수록 빠른 발놀림"),
                ("step", "보폭 STEP (cm)", 0, 14, 8, "한 주기에 나아가는 거리"),
                ("lift", "발 드는 높이 LIFT (cm)", 0, 12, 8, "0 이면 발이 끌려요"),
                ("height", "딛는 깊이 HEIGHT (cm)", 24, 36, 31, "엉덩이 관절 아래로")]:
            r = ttk.Frame(tab)
            r.pack(fill="x", pady=2)
            ttk.Label(r, text=text, font=UI_BOLD, width=22).pack(side="left")
            var = tk.DoubleVar(value=init)
            ttk.Scale(r, from_=lo, to=hi, variable=var, length=220,
                      command=lambda v: self._on_gait_slider()).pack(side="left", padx=4)
            lbl = ttk.Label(r, text="", width=6)
            lbl.pack(side="left")
            ttk.Label(r, text=note, font=SMALL, foreground="#666").pack(side="left")
            self.g[key] = (var, lbl)
        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="▶ 걷기 시작", command=lambda: self._gait(True)).pack(side="left")
        ttk.Button(btns, text="■ 멈추기", command=lambda: self._gait(False)).pack(side="left", padx=6)
        self.speed_lbl = ttk.Label(btns, text="", font=UI_BOLD)
        self.speed_lbl.pack(side="left", padx=10)
        self.gait_cv = tk.Canvas(tab, width=420, height=230, background="white", highlightthickness=1,
                                 highlightbackground="#ccc")
        self.gait_cv.pack(pady=4)
        ttk.Label(tab, text="실험: kp 를 60 아래로 낮추고 걸어 보세요. 왜 뒤로 갈까요?  LIFT 를 0 으로 하면?",
                  font=SMALL, foreground="#a05000").pack(anchor="w")
        self._on_gait_slider(send=False)

    def _gait_params(self):
        T = round(self.g["T"][0].get(), 2)
        step = round(self.g["step"][0].get()) / 100
        lift = round(self.g["lift"][0].get()) / 100
        height = -round(self.g["height"][0].get()) / 100
        return T, step, lift, height

    def _on_gait_slider(self, send=True):
        T, step, lift, height = self._gait_params()
        self.g["T"][1].configure(text=f"{T:.2f}")
        self.g["step"][1].configure(text=f"{step * 100:.0f}")
        self.g["lift"][1].configure(text=f"{lift * 100:.0f}")
        self.g["height"][1].configure(text=f"{-height * 100:.0f}")
        self.speed_lbl.configure(text=f"이론 속도 = 보폭 ÷ 주기 = {step / T * 100:.0f} cm/s")
        self._draw_gait(T, step, lift, height)
        self._refresh_code()
        if send and self.state and self.state.get("gait"):
            self._queue({"op": "gait", "on": True, "T": T, "step": step, "lift": lift, "height": height})

    def _draw_gait(self, T, step, lift, height):
        c = self.gait_cv
        c.delete("all")
        s, ox, gy = 1400, 210, 170                   # 1 m = 1400 px, 바닥 높이 gy
        c.create_text(414, 10, text="한 다리 발끝이 한 주기 동안 그리는 길 (옆에서 본 모습, 앞 →)", anchor="e",
                      font=SMALL, fill="#777")
        pts = []
        for i in range(61):
            x, z = trot_feet(i / 60 * T, T, step, lift, height)["FL"]
            pts.append((ox + (x - 0.02) * s, gy - (z - height) * s))
        stance, swing = pts[:31], pts[30:]
        c.create_line(*[v for p in stance for v in p], fill="#8b5a2b", width=4, arrow="last")
        c.create_line(*[v for p in swing for v in p], fill="#2e8b57", width=4, arrow="last", smooth=True)
        c.create_line(20, gy + 6, 400, gy + 6, fill="#999")
        c.create_text(24, gy + 18, text="바닥", anchor="w", font=SMALL, fill="#999")
        c.create_text(ox, gy + 22, text=f"보폭 {step * 100:.0f} cm", font=SMALL, fill="#8b5a2b")
        c.create_text(ox, gy - lift * s - 14, text=f"드는 높이 {lift * 100:.0f} cm", font=SMALL, fill="#2e8b57")

    def _gait(self, on):
        if on:
            T, step, lift, height = self._gait_params()
            self._send({"op": "gait", "on": True, "T": T, "step": step, "lift": lift, "height": height})
        else:
            self._send({"op": "gait", "on": False})
            self.goal = None                          # 멈춘 자세를 다음 상태에서 받아 옴

    # ================= 코드 보기 =================
    def _build_code_box(self):
        box = ttk.LabelFrame(self.win, text="코드로 쓰면 이렇게 돼요", padding=6)
        box.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        ttk.Button(box, text="편집기에 넣기", command=self._insert_code).pack(side="bottom", anchor="e", pady=(4, 0))
        self.code_txt = tk.Text(box, height=5, font=MONO, background="#f7f7f7", relief="flat", wrap="none")
        self.code_txt.pack(fill="x")

    def _code_lines(self):
        tab = self.nb.index(self.nb.select()) if self.nb.select() else 0
        if tab == 0:
            j = self.last_joint
            legs = LEGS if self.all_legs.get() else [self.leg_var.get()]
            deg = round(self.sliders[j].get())
            lines = [f'dog.set_angle("{leg}", "{j}", {deg})' for leg in legs]
            idx, name = official_name(legs[0], j)
            comment = [f"# {LEG_NAMES[legs[0]]} 다리 '{JOINT_INFO[j][0]}' 관절을 {deg}° 로",
                       f"# 공식 형식: 관절 {idx}번 {name} 목표각 {math.radians(deg):.3f} rad (12×5 명령의 2번째 열)"]
            return comment + lines
        if tab == 1:
            x, z = self._foot_xz()
            sel = self.foot_target.get()
            head = [f"# 발끝을 엉덩이 관절에서 앞으로 {x * 100:.0f} cm, 아래로 {-z * 100:.0f} cm 에",
                    "# 코드에서는 m 단위라서 cm ÷ 100 →  x = %.2f, z = %.2f" % (x, z)]
            if sel == "all":
                return head + [f"dog.set_feet({{leg: ({x:.2f}, {z:.2f}) for leg in LEGS}}, seconds=0.8)"]
            return head + [f'dog.set_feet({{"{sel}": ({x:.2f}, {z:.2f})}}, seconds=0.8)']
        T, step, lift, height = self._gait_params()
        return ["# J5 걸음새 샘플의 맨 위 값들", f"T = {T}          # 한 주기 시간 (초)",
                f"STEP = {step:.2f}      # 보폭 (m)", f"LIFT = {lift:.2f}      # 발 드는 높이 (m)",
                f"HEIGHT = {height:.2f}   # 딛는 발의 높이 (m)"]

    def _refresh_code(self):
        if not hasattr(self, "code_txt"):          # 화면을 만드는 중
            return
        self.code_txt.configure(state="normal")
        self.code_txt.delete("1.0", "end")
        self.code_txt.insert("1.0", "\n".join(self._code_lines()))
        self.code_txt.configure(state="disabled")

    def _insert_code(self):
        lines = [l for l in self._code_lines()]
        self.studio.insert_code("\n".join(lines) + "\n")

    # ================= 명령 보내기 =================
    def pose(self, name):
        self.goal = pose_degrees(name)
        self._sync_sliders()
        self._send({"op": "pose", "name": name})

    def _on_kp(self):
        kp = round(self.kp_var.get())
        self.kp_lbl.configure(text=str(kp))
        if not self._updating:
            self._queue({"op": "stiffness", "kp": kp})

    def _queue(self, msg):
        """슬라이더를 끄는 동안 너무 자주 보내지 않도록 50 ms 마다 마지막 값만 보낸다."""
        self._pending = msg
        if self._send_job is None:
            self._send_job = self.win.after(SEND_EVERY_MS, self._flush)

    def _flush(self):
        self._send_job = None
        if self._pending:
            self._send(self._pending)
            self._pending = None

    def _send(self, msg):
        if self.studio.running:
            self.status_lbl.configure(text="코드 실행 중에는 조작 패널을 쓸 수 없어요 (■ 정지 후 사용)")
            return
        self.studio.send_panel(msg)

    # ================= 상태 받기 =================
    def on_state(self, st):
        self.state = st
        if self.goal is None or len(self.goal) != 12:
            self.goal = list(st["target"])
            self._sync_sliders()
        r, p, _ = st["rpy"]
        mode = {"joint": "관절 조작", "walk": "보행 정책(Robot API)", "standup": "일어서는 중", "lie": "엎드림"}
        self.status_lbl.configure(
            text=f"몸 높이 {st['height'] * 100:.0f} cm   ·   기울기 좌우 {r:+.0f}° 앞뒤 {p:+.0f}°   ·   "
                 f"{mode.get(st['mode'], st['mode'])}{'  ·  걷는 중' if st.get('gait') else ''}")
        self._draw_forces(st["fz"])
        if abs(self.kp_var.get() - st["kp"]) > 0.5 and self._pending is None:
            self._updating = True
            self.kp_var.set(st["kp"])
            self.kp_lbl.configure(text=str(round(st["kp"])))
            self._updating = False
        i = LEGS.index(self.leg_var.get()) * 3
        q, t = st["q"], st["target"]
        for k, j in enumerate(JOINTS):
            self.val_lbls[j].configure(text=f"목표 {t[i + k]:6.1f}°  실제 {q[i + k]:6.1f}°")
        self.side_view.draw((q[i + 1], q[i + 2]), target=(t[i + 1], t[i + 2]))
        self.front_view.draw(q[i], target=t[i])

    def resync(self):
        """코드 실행·초기화 뒤: 다음 상태에서 목표값을 다시 받아 온다."""
        self.goal = None

    def close(self):
        self.studio.panel = None
        self.win.destroy()
