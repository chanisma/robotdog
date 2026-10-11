# robotdog — DEEP Robotics Lite3 Pro 교육·연구 프로젝트

DEEP Robotics **Jueying Lite3 Pro** 4족 보행 로봇을 활용한 로봇 교육 과정 개발과 연구 환경 구축 프로젝트.

## 폴더 구조
```
docs/
  knowledge/                 # Lite3 지식 베이스 (사실, 출처 기반)
    01_hardware.md             사양, 센서, 인터페이스, 관절 순서, LED, 보증
    02_system_architecture.md  모션 호스트와 인지 호스트, IP·포트, UDP SDK, ROS2 토픽
    03_software_ecosystem.md   공식 GitHub 저장소, 학습→배포 파이프라인, 버전 지도
    04_app_and_controller.md   공식 앱과 리모컨 기능, 확장 지점, 교육 응용 아이디어
    05_safety.md               안전 수칙, 비상 대응, 수업 운영 규칙
  plan/                      # 계획
    roadmap.md                 Phase 0–6 개발·연구 준비 로드맵
    curriculum.md              고등학생 교육 과정 (16차시: 앱 조작 → 센서 → Python 조작 → AI 미리보기)
    edu_python_api.md          학생용 Python 라이브러리 lite3_edu 설계안 (mock, sim, real)
    advanced_joint_and_diy.md  심화: 관절 제어 → 걸음새, DYNAMIXEL DIY 로봇개 계획
    unit_checklist.md          실물 수령 후 확인할 항목
  references.md              출처, 아직 확보하지 못한 문서
sim/proto/                   Lite3 Studio(편집기+3D 시뮬레이터), 학생 API, 예제 J1–J5
scripts/clone_upstream.sh    공식 저장소 클론 스크립트
third_party/                 공식 저장소 (git 추적 제외)
```
진행하면서 `deploy/`(실물 배포 설정), `edu/`(교재·학생용 API), `docker/`를 추가할 예정이다.

## 빠른 시작
1. 안전 수칙을 숙지한다: [`docs/knowledge/05_safety.md`](docs/knowledge/05_safety.md)
2. 공식 저장소를 받는다: `bash scripts/clone_upstream.sh`
3. 로드맵 Phase 0부터 진행한다: [`docs/plan/roadmap.md`](docs/plan/roadmap.md)
