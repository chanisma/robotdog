"""Lite3 코드 스튜디오 — 코드를 쓰고 ▶ 실행하면 3D 시뮬레이터에서 로봇이 움직인다.

실행: ../../.venv/Scripts/python studio.py   (또는 run_studio.bat 더블클릭)
3D 화면을 켜면 시뮬레이터(sim_server.py)를 켜 둔 채 코드만 보낸다 → 로봇 상태가 실행 사이에 이어진다.
3D 화면을 끄면 화면 없이 한 번 실행해 결과만 빠르게 본다. 어느 쪽이든 ■ 정지로 무한 반복도 멈춘다.
"""
import json
import keyword
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from control_panel import ControlPanel

HERE = Path(__file__).resolve().parent
EVENT_PREFIX = "\x01EVT "                 # sim_server.py 와 같은 값
LESSONS = HERE / "joint_lessons"

SAMPLES = {
    "기본 — 정사각형 걷기 (Robot API)": HERE / "demo_square.py",
    "J1 — 모터 하나 움직이기": LESSONS / "j1_one_motor.py",
    "J2 — 자세 (엎드리기·서기·앉기)": LESSONS / "j2_poses.py",
    "J3 — 각도 ↔ 발 위치 (기구학)": LESSONS / "j3_kinematics.py",
    "J4 — 다리 하나 들기 (무게중심)": LESSONS / "j4_lift_leg.py",
    "J5 — 걸음새 직접 만들기 (트롯)": LESSONS / "j5_trot.py",
}

UI_FONT = ("Malgun Gothic", 10)
CODE_FONT = ("Consolas", 12)
COLORS = {"keyword": "#0000cc", "string": "#a31515", "comment": "#008000",
          "number": "#098658", "builtin": "#795e26"}
TOKEN_RE = re.compile(
    r"(?P<comment>#[^\n]*)"
    r"|(?P<string>\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|\"[^\"\n]*\"|'[^'\n]*')"
    r"|(?P<keyword>\b(?:" + "|".join(keyword.kwlist) + r")\b)"
    r"|(?P<builtin>\b(?:print|range|len|round|int|float|str|list|dict|abs|min|max)\b)"
    r"|(?P<number>\b\d+(?:\.\d+)?\b)"
)


class Studio:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.out_queue = queue.Queue()
        self.workdir = Path(tempfile.mkdtemp(prefix="lite3_studio_"))
        self.code_file = self.workdir / "my_code.py"
        self.loaded_sample = None
        self.stopped = False
        self.running = False
        self.run_id = 0
        self.server = None                     # 라이브 시뮬레이터 (sim_server.py)
        self.pending_code = None               # 시뮬레이터가 켜지면 보낼 코드
        self.panel = None                      # 조작 패널 창

        root.title("Lite3 코드 스튜디오")
        root.geometry("1000x760")
        root.minsize(720, 520)
        self._build_toolbar()
        self._build_editor()
        self._build_console()
        self._bind_keys()

        self.sample_box.current(1)
        self.load_sample()
        self.root.after(50, self._poll_output)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- 화면 구성 ----------
    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Label(bar, text="샘플", font=UI_FONT).pack(side="left")
        self.sample_box = ttk.Combobox(bar, values=list(SAMPLES), state="readonly", width=34, font=UI_FONT)
        self.sample_box.pack(side="left", padx=(6, 4))
        self.sample_box.bind("<<ComboboxSelected>>", lambda e: self.load_sample())
        ttk.Button(bar, text="원래대로", command=self.load_sample).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="열기", command=self.open_file).pack(side="left")
        ttk.Button(bar, text="저장", command=self.save_file).pack(side="left", padx=(4, 0))

        self.run_btn = ttk.Button(bar, text="▶ 실행 (F5)", command=self.run)
        self.stop_btn = ttk.Button(bar, text="■ 정지 (Esc)", command=self.stop, state="disabled")
        self.stop_btn.pack(side="right")
        self.run_btn.pack(side="right", padx=4)
        ttk.Button(bar, text="↺ 처음 자세", command=self.reset_robot).pack(side="right", padx=(0, 4))
        ttk.Button(bar, text="🎛 조작 패널", command=self.open_panel).pack(side="right", padx=(0, 4))
        self.view_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="3D 화면", variable=self.view_var).pack(side="right", padx=8)

    def _build_editor(self):
        pane = ttk.PanedWindow(self.root, orient="vertical")
        pane.pack(fill="both", expand=True, padx=8)
        self.pane = pane

        frame = ttk.Frame(pane)
        self.gutter = tk.Text(frame, width=4, padx=4, takefocus=0, border=0, background="#f0f0f0",
                              foreground="#888", state="disabled", font=CODE_FONT)
        self.gutter.pack(side="left", fill="y")
        self.editor = tk.Text(frame, wrap="none", undo=True, font=CODE_FONT, tabs=("1c",))
        yscroll = ttk.Scrollbar(frame, command=self._scroll_both)
        self.editor.configure(yscrollcommand=lambda *a: (yscroll.set(*a), self.gutter.yview_moveto(a[0])))
        yscroll.pack(side="right", fill="y")
        self.editor.pack(side="left", fill="both", expand=True)
        for tag, color in COLORS.items():
            self.editor.tag_configure(tag, foreground=color)
        self.editor.tag_configure("errorline", background="#ffe0e0")
        pane.add(frame, weight=3)

    def _build_console(self):
        frame = ttk.Frame(self.pane)
        head = ttk.Frame(frame)
        head.pack(fill="x")
        ttk.Label(head, text="출력", font=UI_FONT).pack(side="left")
        self.status = ttk.Label(head, text="준비", font=UI_FONT, foreground="#555")
        self.status.pack(side="left", padx=10)
        self.sim_label = ttk.Label(head, text="○ 시뮬레이터 꺼짐", font=UI_FONT, foreground="#888")
        self.sim_label.pack(side="left", padx=10)
        ttk.Button(head, text="지우기", command=self.clear_console).pack(side="right")
        self.console = tk.Text(frame, height=10, font=("Consolas", 11), background="#1e1e1e",
                               foreground="#dddddd", insertbackground="white", state="disabled")
        self.console.pack(fill="both", expand=True, pady=(2, 8))
        self.console.tag_configure("err", foreground="#ff6b6b")
        self.console.tag_configure("info", foreground="#6cb6ff")
        self.pane.add(frame, weight=1)

    def _bind_keys(self):
        self.root.bind("<F5>", lambda e: self.run())
        self.root.bind("<Escape>", lambda e: self.stop())
        self.root.bind("<Control-s>", lambda e: (self.save_file(), "break")[1])
        self.editor.bind("<Tab>", lambda e: (self.editor.insert("insert", "    "), "break")[1])
        self.editor.bind("<Return>", self._auto_indent)
        self.editor.bind("<<Modified>>", self._on_modified)

    # ---------- 편집기 ----------
    def _scroll_both(self, *args):
        self.editor.yview(*args)
        self.gutter.yview(*args)

    def _auto_indent(self, _event):
        line = self.editor.get("insert linestart", "insert")
        indent = re.match(r"[ ]*", line).group()
        if line.rstrip().endswith(":"):
            indent += "    "
        self.editor.insert("insert", "\n" + indent)
        self.editor.see("insert")
        return "break"

    def _on_modified(self, _event):
        if self.editor.edit_modified():
            self.editor.edit_modified(False)
            self._highlight()
            self._update_gutter()

    def _highlight(self):
        text = self.editor.get("1.0", "end-1c")
        for tag in COLORS:
            self.editor.tag_remove(tag, "1.0", "end")
        for m in TOKEN_RE.finditer(text):
            self.editor.tag_add(m.lastgroup, f"1.0+{m.start()}c", f"1.0+{m.end()}c")

    def _update_gutter(self):
        n = int(self.editor.index("end-1c").split(".")[0])
        self.gutter.configure(state="normal")
        self.gutter.delete("1.0", "end")
        self.gutter.insert("1.0", "\n".join(str(i) for i in range(1, n + 1)))
        self.gutter.configure(state="disabled")
        self.gutter.yview_moveto(self.editor.yview()[0])

    def set_code(self, code):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", code)
        self.editor.edit_reset()
        self.editor.tag_remove("errorline", "1.0", "end")
        self._highlight()
        self._update_gutter()

    def get_code(self):
        return self.editor.get("1.0", "end-1c")

    # ---------- 파일 ----------
    def load_sample(self):
        name = self.sample_box.get()
        self.loaded_sample = SAMPLES[name]
        self.set_code(self.loaded_sample.read_text(encoding="utf-8"))
        self.status.configure(text=f"샘플 불러옴: {name}")

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Python", "*.py")], initialdir=HERE)
        if path:
            self.set_code(Path(path).read_text(encoding="utf-8"))
            self.status.configure(text=f"열기: {Path(path).name}")

    def save_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("Python", "*.py")],
                                            initialdir=Path.home() / "Documents", initialfile="my_robot.py")
        if path:
            Path(path).write_text(self.get_code(), encoding="utf-8")
            self.status.configure(text=f"저장: {Path(path).name}")

    # ---------- 실행 ----------
    def run(self):
        """3D 화면을 켜면 켜져 있는 시뮬레이터(sim_server)에 코드를 보내고,
        끄면 화면 없이 한 번 실행해 결과만 빠르게 본다."""
        if self.running:
            self.write_console("이미 실행 중이에요. ■ 정지 후 다시 실행하세요.\n", "info")
            return
        self.editor.tag_remove("errorline", "1.0", "end")
        self.stopped = False
        code = self.get_code()
        self._set_running(True)
        if self.view_var.get():
            if self._server_alive():
                self._send({"cmd": "run", "code": code})
            else:
                self.pending_code = code
                self._start_server()
                self.write_console("3D 시뮬레이터를 켜는 중…\n", "info")
        else:
            self._run_once(code)

    def stop(self):
        if not self.running:
            return
        self.stopped = True
        if self.proc and self.proc.poll() is None and self.proc is not self.server:
            self.proc.kill()                     # 화면 없는 한 번 실행
        elif self._server_alive():
            self._send({"cmd": "stop"})
            self.root.after(3000, self._kill_if_unresponsive, self.run_id)

    def reset_robot(self):
        if self.running:
            self.write_console("실행 중에는 초기화할 수 없어요. 먼저 ■ 정지하세요.\n", "info")
        elif self._server_alive():
            self._send({"cmd": "reset"})
        else:
            self.write_console("3D 시뮬레이터가 꺼져 있어요. ▶ 실행하면 처음 자세로 켜져요.\n", "info")

    # --- 조작 패널 ---
    def open_panel(self):
        if self.panel:
            self.panel.win.lift()
            return
        self.panel = ControlPanel(self)
        if not self._server_alive():
            self._start_server()
            self.write_console("3D 시뮬레이터를 켜는 중… (조작 패널)\n", "info")

    def send_panel(self, msg):
        if self._server_alive():
            self._send({"cmd": "panel", **msg})

    def insert_code(self, text):
        self.editor.insert("insert", text)
        self.editor.see("insert")
        self._highlight()
        self._update_gutter()
        self.editor.focus_set()

    # --- 화면 없는 한 번 실행 ---
    def _run_once(self, code):
        self.code_file.write_text(code, encoding="utf-8")
        args = [sys.executable, "-u", str(self.code_file), "--no-view"]
        self.proc = self._spawn(args)
        self.write_console("▶ 실행 시작 (화면 없이)\n", "info")

    # --- 라이브 시뮬레이터 ---
    def _start_server(self):
        self.server = self._spawn([sys.executable, "-u", str(HERE / "sim_server.py")], stdin=True)
        self.proc = self.server
        self.sim_label.configure(text="● 시뮬레이터 켜는 중", foreground="#c08000")

    def _server_alive(self):
        return self.server is not None and self.server.poll() is None

    def _send(self, msg):
        try:
            self.server.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            self.server.stdin.flush()
        except OSError:
            self.write_console("시뮬레이터와 연결이 끊겼어요.\n", "err")

    def _kill_if_unresponsive(self, run_id):
        if self.running and run_id == self.run_id and self._server_alive():
            self.write_console("응답이 없어 시뮬레이터를 껐어요. 다음 실행 때 새로 켜져요.\n", "err")
            self.server.kill()

    def _spawn(self, args, stdin=False):
        env = dict(os.environ, PYTHONIOENCODING="utf-8",
                   PYTHONPATH=os.pathsep.join([str(HERE), str(LESSONS)]))
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(args, cwd=self.workdir, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.PIPE if stdin else None,
                                creationflags=flags)
        threading.Thread(target=self._reader, args=(proc,), daemon=True).start()
        return proc

    def _reader(self, proc):
        for raw in proc.stdout:
            self.out_queue.put((proc, "line", raw.decode("utf-8", errors="replace")))
        proc.wait()
        self.out_queue.put((proc, "exit", proc.returncode))

    def _poll_output(self):
        try:
            while True:
                proc, kind, value = self.out_queue.get_nowait()
                if proc is not self.proc and proc is not self.server:
                    continue                     # 이전에 정지한 프로그램이 늦게 보낸 출력은 버림
                if kind == "line" and value.startswith(EVENT_PREFIX):
                    self._on_event(json.loads(value[len(EVENT_PREFIX):]))
                elif kind == "line":
                    self._show_line(value)
                elif proc is self.server:
                    self._on_server_exit()
                else:
                    self._on_once_exit(value)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_output)

    def _on_event(self, ev):
        name = ev["event"]
        if name == "state":
            if self.panel:
                self.panel.on_state(ev)
            return
        if name in ("run_end", "reset_done") and self.panel:
            self.panel.resync()
        if name == "ready":
            self.sim_label.configure(text="● 시뮬레이터 켜짐", foreground="#2e8b57")
            if self.pending_code is not None:
                self._send({"cmd": "run", "code": self.pending_code})
                self.pending_code = None
        elif name == "run_start":
            self.write_console("▶ 실행 시작\n", "info")
            self.status.configure(text="실행 중… (■ 정지로 멈춤)")
        elif name == "run_end":
            st = ev.get("status")
            if st == "ok":
                self.write_console("✔ 끝! 로봇은 지금 자세 그대로 기다려요. 코드를 고쳐 이어서 실행해 보세요.\n", "info")
            elif st == "stopped":
                self.write_console("■ 정지했어요\n", "info")
            else:
                self.write_console("✖ 오류로 멈췄어요. 편집기의 빨간 줄을 확인하세요.\n", "err")
            self.status.configure(text={"ok": "준비", "stopped": "정지됨"}.get(st, "오류"))
            self._set_running(False)
        elif name == "reset_done":
            self.write_console("↺ 로봇을 처음 자세(엎드림)로 되돌렸어요\n", "info")
        elif name == "busy":
            self.write_console("시뮬레이터가 아직 바빠요. 잠시 후 다시 시도하세요.\n", "info")

    def _on_server_exit(self):
        self.server = None
        self.sim_label.configure(text="○ 시뮬레이터 꺼짐", foreground="#888")
        if self.running:
            self.write_console("■ 시뮬레이터가 종료되어 실행을 멈췄어요\n", "info")
            self._set_running(False)
            self.status.configure(text="정지됨")
        else:
            self.write_console("3D 창이 닫혔어요. 다음 ▶ 실행 때 다시 켜져요.\n", "info")

    def _on_once_exit(self, code):
        if code == 0:
            self.write_console("✔ 프로그램이 끝났어요\n", "info")
            self.status.configure(text="준비")
        elif self.stopped:
            self.write_console("■ 정지했어요\n", "info")
            self.status.configure(text="정지됨")
        else:
            self.write_console("✖ 오류로 멈췄어요. 편집기의 빨간 줄을 확인하세요.\n", "err")
            self.status.configure(text="오류")
        self._set_running(False)

    def _set_running(self, running):
        self.running = running
        if running:
            self.run_id += 1
        self.run_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")

    def _show_line(self, line):
        line = line.replace(str(self.code_file), "내 코드")
        is_err = line.startswith(("Traceback", "  File", "    ")) or re.match(r"^\w+(Error|Exception)\b", line)
        m = re.search(r'File "내 코드", line (\d+)', line)
        if m:
            n = m.group(1)
            self.editor.tag_add("errorline", f"{n}.0", f"{n}.end+1c")
            self.editor.see(f"{n}.0")
            line = line.replace(f'File "내 코드", line {n}', f"내 코드 {n}번째 줄")
        self.write_console(line, "err" if is_err else None)

    # ---------- 콘솔 ----------
    def write_console(self, text, tag=None):
        self.console.configure(state="normal")
        self.console.insert("end", text, tag)
        self.console.see("end")
        self.console.configure(state="disabled")

    def clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def on_close(self):
        if self.running and not messagebox.askokcancel("종료", "실행 중인 프로그램이 있어요. 멈추고 닫을까요?"):
            return
        for proc in (self.proc, self.server):
            if proc and proc.poll() is None:
                proc.kill()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    Studio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
