"""라이브 모드: 이미 켜져 있는 시뮬레이터(sim_server.py)에 학생 API를 연결한다.

sim_server 가 CONTEXT 를 설정하면 Robot / JointDog 는 새 시뮬·창을 만들지 않고
CONTEXT.sim 을 같이 쓰며, 시간 진행은 CONTEXT.advance() 로 서버 메인 루프에 맡긴다.

동기화 규칙: 학생 코드 스레드는 실행되는 동안 lock 을 쥐고 있고,
advance(n) 에서만 lock 을 놓고 서버가 n 스텝을 진행하기를 기다린다.
그래서 물리 계산·화면 갱신과 학생 코드가 시뮬 데이터를 동시에 건드리지 않는다.
"""
import threading

CONTEXT = None


class StopRun(Exception):
    """■ 정지 버튼으로 학생 코드를 멈출 때 쓰는 예외."""


class LiveContext:
    def __init__(self, sim):
        self.sim = sim
        self.lock = threading.Lock()
        self.remaining = 0                   # 서버가 더 진행해야 할 스텝 수
        self.done = threading.Event()
        self.stop_flag = False

    def advance(self, steps):
        """(학생 코드 스레드에서 호출) 서버 메인 루프가 steps 만큼 시뮬을 진행할 때까지 기다린다."""
        if self.stop_flag:
            raise StopRun
        self.done.clear()
        self.remaining = steps
        self.lock.release()
        try:
            while not self.done.wait(0.05):
                if self.stop_flag:
                    break
        finally:
            self.lock.acquire()
            self.remaining = 0
        if self.stop_flag:
            raise StopRun
