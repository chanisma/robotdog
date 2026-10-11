# 03. 소프트웨어 생태계 (DeepRoboticsLab GitHub)

조사일: 2026-10-11 · 조직: https://github.com/DeepRoboticsLab (저장소 28개)

## 1. Lite3에 쓸 핵심 저장소

| 저장소 | 용도 | 상태 | 비고 |
|---|---|---|---|
| **sdk_deploy** | sim-to-sim / sim-to-real 통합 배포 (Lite3, M20, M20S, S10) | ✅ 최신 (2026-09) | `src/Lite3_sdk_deploy`, `lite3_sdk_service`(SDK 모드 전환과 주파수 설정), `lite3_transfer`(UDP↔ROS2). 키보드, 게임패드, ROS2 입력. 상태 10 Hz, 명령 50 Hz |
| **Lite3_rl_deploy** | Lite3 전용 RL 정책 배포 | ✅ 유지 (2026-09) | MuJoCo·PyBullet 시뮬. ONNX 정책. 상태 머신 Idle→StandUp→RL→JointDamping/LieDown |
| **rl_training** | Isaac Lab 기반 RL 학습 | ✅ 최신 (2026-09) | 작업 `Rough-Deeprobotics-Lite3-v0`. Isaac Sim 5.1.0, Isaac Lab 2.3.2, Python 3.11, RSL-RL 5.0.1, Ubuntu 22.04. ONNX 내보내기: `scripts/tools/export_onnx_fast.py --robot lite3` |
| **deep_robotics_model** | URDF / MJCF / USD 모델 | ✅ (2026-09) | 고해상도 모델은 Google Drive에 있음. 웹 뷰어: viewer.robotsfan.com |
| **Lite3_ROS** | ROS ↔ UDP 브리지 | 🟡 (2026-02) | 브랜치 `ros2-foxy`(Ubuntu 20.04). ROS1 Ubuntu 18/20 버전도 있음 |
| **gamepad** | 공식 리모컨(Retroid) 버튼 이벤트를 UDP로 수신하는 C++ 라이브러리 | 🟡 (2025-10) | 기본 포트 `12121`. 리모컨에 `controlapp.apk`가 필요함 → 04 문서 |
| **Robot_Training_Cases** | **공식 교육 실습 11종**(중국어) | 🟡 (2025-10) | LiDAR 에디션 기준 → 05 계획 문서에 대응표 정리 |
| Lite3_MotionSDK | 구형 관절 SDK (MPC 예제) | ⛔ 지원 종료 | 문서와 데이터 구조 참고용으로만 씀. 대신 rl_deploy와 sdk_deploy 사용 |

## 2. 응용과 참고 저장소

| 저장소 | 내용 |
|---|---|
| Lite3_LLM | Qwen-VL과 YOLOv8, RealSense로 자연어 명령을 `/cmd_vel`과 `llm_control`(Int32 액션 코드)로 바꿈. ROS1. 교육용 LLM 실습의 원형 |
| Lite3_Navigation | ROS1 Noetic 기반 hdl_localization, move_base, TEB 내비게이션(LiDAR 필요) |
| Lite3_SLAM | SLAM (LiDAR 필요) |
| Lite3_Track | 사람 추종 |
| Lite3_VMC | VMC(Virtual Model Control) 기반 모션 제어 예제 |
| Lite3_rl_training | 구형 RL 학습. rl_training으로 대체됨 |
| lightning-lm-deep-robotics | LiDAR 위치 추정과 매핑 (Lite3 EDU 지원) |
| deep-robotics-sdk2 / -simulation / -mimic / -retarget / -teleoperate / -msg | 2026년에 새로 생긴 저장소(설명 없음). 주로 차세대 기종용이며 Lite3 지원 여부는 확인 필요 |
| deep-research | 커뮤니티 2차 개발 사례(현재는 Lynx S10 중심) |

## 3. 표준 개발 파이프라인

```
URDF/MJCF (deep_robotics_model)
        │
        ▼
 Isaac Lab 학습 (rl_training) ──▶ .pt ──▶ ONNX 내보내기
        │                                      │
        ▼                                      ▼
  play / 시각 검증                 sim2sim: MuJoCo (Lite3_rl_deploy / sdk_deploy)
                                               │  키보드·Xbox 패드로 검증
                                               ▼
                               sim2real: scp로 모션 호스트(ARM)에 복사
                               -DBUILD_PLATFORM=arm -DBUILD_SIM=OFF 로 빌드
                               ./rl_deploy 실행 (Retroid 리모컨: Y 서기, A RL, X 눕기)
```

### Lite3_rl_deploy 빌드 옵션
| 대상 | cmake 옵션 |
|---|---|
| PC 시뮬 | `-DBUILD_PLATFORM=x86 -DBUILD_SIM=ON -DSEND_REMOTE=OFF` |
| 실물 | `-DBUILD_PLATFORM=arm -DBUILD_SIM=OFF -DSEND_REMOTE=OFF` |

의존성: Python 3.10, `pybullet`, `mujoco`, `numpy<2`, `libdw-dev`. ONNX 변환에는 `torch`, `onnx`, `onnxruntime`이 필요하다.

### 조작키 (rl_deploy)
| 동작 | 키보드 | Xbox (시뮬) | Retroid (실물) |
|---|---|---|---|
| 서기 | z | LB | Y |
| RL 모드 | c | RB | A |
| 눕기 | x | X | X |
| 댐핑 | r | LT | 양쪽 스틱 누르기 |
| 이동 / 회전 | w a s d / q e | 왼쪽 스틱 / 오른쪽 스틱 | 왼쪽 스틱 / 오른쪽 스틱 |

## 4. 개발 환경 버전 지도

| 영역 | 권장 환경 |
|---|---|
| RL 학습 | Ubuntu 22.04, NVIDIA RTX GPU(VRAM 12 GB 이상 권장), Isaac Sim 5.1 / Isaac Lab 2.3.2, conda 환경(Python 3.11) |
| 배포 시뮬 | Ubuntu 22.04 (WSL2도 MuJoCo는 가능), Python 3.10 |
| ROS2 연동 | 로봇 쪽은 Foxy(20.04). PC 쪽 Humble과는 DDS 호환성을 확인해야 함 → 처음에는 **인지 호스트 안에서 직접 실행**하거나 Foxy 컨테이너를 쓰는 편이 안전 |
| 모션 호스트 | ARM. 로봇에서 직접 빌드 |
