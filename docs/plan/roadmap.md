# 개발·연구 준비 로드맵

목표: Lite3 Pro를 활용한 **로봇 교육 과정**을 운영하고, 그 기반이 되는 개발·연구 환경을 마련한다.

## Phase 0 — 수령과 기준선 확보 (1주)
- [ ] [`unit_checklist.md`](unit_checklist.md)로 실물 정보를 기록한다(펌웨어, IP, 계정, SSID, MAC).
- [ ] DEEP Robotics 기술지원에 요청할 것:
  - **인지 개발 매뉴얼(Perception Development Manual) 최신판**
  - **통신 프로토콜 문서**
  - Pro 에디션에서 Auto Mode 지원 여부
  - RTSP URL
  - 인지 호스트 계정
- [ ] 기본 비밀번호(Wi-Fi, SSH)를 바꾸고 교실 네트워크 방식을 정한다.
- [ ] 안전 장비를 준비한다: 매트, 펜스·콘, **호이스트(매달기용 프레임)**, 소화기.
- [ ] 앱으로 기본 조작에 익숙해진다(보행, 액션, Smart Sensing 전부).

## Phase 1 — 개발 환경 구축 (1–2주)
| 장비 | 용도 | 권장 사양 |
|---|---|---|
| 학습 워크스테이션 | Isaac Lab 기반 RL 학습 | Ubuntu 22.04, RTX 4080 이상 (VRAM 16 GB 이상), RAM 64 GB |
| 개발 노트북 | 시뮬, ROS2, 로봇 접속 | Ubuntu 22.04 네이티브 권장. Windows라면 WSL2(MuJoCo, ROS2 정도만) |
| 학생 PC | 시뮬 실습 | MuJoCo가 돌아가는 일반 PC. Docker 이미지로 배포 |

- [ ] `scripts/clone_upstream.sh`로 공식 저장소를 `third_party/`에 받는다.
- [ ] Docker 이미지 2종을 만든다:
  - `sim`: Ubuntu 22.04, Python 3.10, mujoco, rl_deploy 빌드 포함
  - `ros2-foxy`: 로봇과 같은 ROS 배포판

## Phase 2 — 시뮬레이션 (실물 없이)
- [ ] deep_robotics_model의 Lite3 URDF와 MJCF를 시각화하고 관절 한계와 effort를 표로 정리한다 → `docs/knowledge/`에 추가.
- [ ] Lite3_rl_deploy를 MuJoCo로 sim2sim 실행한다(키보드 z → c → wasd).
- [ ] sdk_deploy의 Lite3 경로도 실행해 보고 두 배포 체계의 차이를 정리한다.

## Phase 3 — 실물 고수준 제어 (ROS2, 안전)
- [ ] SSH로 인지 호스트에 접속해 `transfer`를 실행하고 `/imu/data`, `/joint_states`, `/leg_odom2`를 **읽기 전용으로** 관찰한다.
- [ ] Auto 모드에서 `/cmd_vel`을 저속(0.1 m/s)으로 보내고, Manual 모드나 STOP으로 제어권을 회수하는 절차를 검증한다.
- [ ] `/simple_cmd`와 `/complex_cmd` 메시지 정의를 분석해 앱 기능 중 코드로 부를 수 있는 것을 목록으로 만든다.
- [ ] gamepad 라이브러리로 리모컨 버튼 이벤트를 PC에서 받는다(앱 확장 A).
- [ ] RTSP 영상을 PC의 OpenCV로 받는다(앱 확장 D).

## Phase 4 — 실물 저수준과 RL 배포 (연구)
- [ ] **호이스트에 매단 상태에서** rl_deploy를 모션 호스트(ARM)에 빌드하고 실행한다. 기본 정책 → 지면 보행 순서로 진행한다.
- [ ] rl_training으로 `Rough-Deeprobotics-Lite3-v0`를 학습 → ONNX로 내보내기 → MuJoCo sim2sim → 실물.
- [ ] 보상과 도메인 랜덤화를 바꿔 보는 실험 템플릿을 만든다(학생 연구 과제용).

## Phase 5 — 응용 (비전, AI)
- [ ] Lite3_LLM을 ROS2와 Claude API로 옮긴다. 허용 목록, 속도 제한, 타임아웃 같은 안전 계층을 둔다.
- [ ] 외부 센서 확장(Livox Mid-360)을 검토한다. Robot_Training_Cases의 SLAM·내비 실습(Case 8, 9)을 하려면 필요하다.

## Phase 6 — 교육 과정 패키징 (고등학생, 기초 Python)
- [ ] **학생용 라이브러리 `lite3_edu`의 mock 백엔드를 먼저 만든다.** 실물 없이 지금 시작할 수 있다 → [`edu_python_api.md`](edu_python_api.md)
- [ ] `real` 게이트웨이(Phase 3 이후)와 `sim` 백엔드(Phase 2와 4 이후)를 만든다.
- [ ] [`curriculum.md`](curriculum.md)의 16차시에 맞춰 활동지, 예제 코드, 조종 면허 평가표를 `edu/`에 정리한다.
- [ ] 1단원(앱 조작)은 실물이 오는 대로 교사가 먼저 리허설한다.

> 우선순위: 기본 과정(1–3단원)에는 Phase 0, Phase 3, 그리고 Phase 6의 mock·real 백엔드만 있으면 된다. Phase 4–5(저수준 제어, RL, AI)는 심화 과정용이므로 뒤로 미룬다.

## 미결정 사항 (의사결정 필요)
1. ~~대상 학습자 수준~~ → **고등학생, 기초 Python으로 결정.** 정확한 차시 수만 남음(초안은 16차시)
2. 학습 워크스테이션 GPU 예산
3. LiDAR(Mid-360) 추가 구매 여부: SLAM·내비 실습 가능 여부가 여기에 달려 있음
4. AI 모션 모드 잠금 해제 여부(보증 기간 단축과 맞바꿈)
