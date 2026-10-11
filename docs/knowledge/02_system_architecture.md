# 02. 시스템 구조와 네트워크

> ⚠️ IP·계정 정보는 펌웨어 버전마다 다를 수 있다. 실물을 받으면 [`../plan/unit_checklist.md`](../plan/unit_checklist.md)로 반드시 확인한다.

## 1. 2-호스트 구조

```
                ┌──────────────────── Lite3 Pro ─────────────────────┐
  [앱/리모컨]    │  ┌──────────────┐   UDP    ┌───────────────────────┐ │
  (Android) ─Wi-Fi─▶│ 모션 호스트    │◀───────▶│ 인지 호스트              │ │
  [E-STOP 리모컨]  │  │ (ARM)        │          │ Jetson Xavier NX       │ │
                │  │ jy_exe       │          │ ROS2 transfer 노드      │ │
                │  │ 보행 제어기    │          │ 카메라 / 깊이 / 초음파    │ │
                │  └──────┬───────┘          └──────────┬────────────┘ │
                │      12 관절 드라이버          USB3 / HDMI / ETH 포트   │
                └─────────────────────────────────────────────────────┘
                         ▲  UDP (SDK)                ▲ ROS2 / SSH
                         └──────── 개발 PC ──────────┘
```

| 호스트 | 역할 | 주소(문서 기준) |
|---|---|---|
| **모션 호스트** | 보행 제어, 관절 제어, 상태 추정. ARM 아키텍처라 **크로스 컴파일 또는 현지 빌드가 필요**하다. 실행 디렉터리는 `~/jy_exe` | `192.168.1.120` (유선 또는 Wi-Fi 1번 대역) / `192.168.2.1` (Wi-Fi 2번 대역) |
| **인지 호스트** | 카메라·깊이·초음파 처리, 추종·회피, ROS2 브리지(`transfer`) | `192.168.1.103` ⚠️ 추정. rl_deploy `network.toml`의 기본 목적지와 노드 이름 `jetson2motion`에서 유추 |
| 내비 호스트 | (X30 전용) `192.168.1.106:30000` | Lite3 Pro에는 해당하지 않음 |

## 2. 접속
- **Wi-Fi**: 보증서 라벨에 SSID와 비밀번호가 적혀 있다. rl_deploy 문서 기준 SSID는 `YSC-JYML-xxxxxx` 형식이고 기본 비밀번호는 `12345678`이다 ⚠️
- **SSH**: `ssh ysc@192.168.1.120` (또는 `192.168.2.1`). 기본 비밀번호는 작은따옴표 한 글자 `'`이다 ⚠️. 연결되지 않으면 계정 `user` 또는 `firefly`도 시도해 본다.
- 개발 PC를 유선으로 연결할 때는 `192.168.1.x` 대역의 고정 IP를 쓴다(예: `192.168.1.200`).
- 🔒 교육 현장에서 쓰기 전에 Wi-Fi와 SSH 기본 비밀번호를 **반드시 바꾼다**(학생 단말이 같은 망에 들어오기 때문).

## 3. 모션 호스트 SDK 통신 (UDP)

| 항목 | 값 |
|---|---|
| 로봇 → 개발자: 상태 데이터 | 목적지 포트 `43897` (`target_port`) |
| 개발자 → 로봇: 관절 명령 | 로봇 포트 `43893` (`local_port`) |
| 설정 파일 | 모션 호스트의 `~/jy_exe/conf/network.toml`. `ips`에 상태 데이터를 받을 개발 PC IP를 적는다. |
| 프로세스 제어 | `~/jy_exe/scripts/` 안의 `stop.sh` / `run.sh` / `restart.sh` |
| 타임아웃 | 명령이 1초 넘게 없으면 자동으로 댐핑 |
| 지연 | Wi-Fi 지연 때문에 500 Hz가 넘는 제어 루프는 불안정하다. 저수준 제어는 **로봇 내부에서 실행하거나 유선으로** 한다. |

`RobotData` 구조
- `imu`: roll / pitch / yaw, 각속도·가속도 각 3축, 타임스탬프
- `joint_data[12]`: 위치, 속도, 토크, 온도
- `contact_force`: 발 4개의 3축 힘
- `tick`

`RobotCmd`: 관절마다 `kp`, `kd`, `position`, `velocity`, `torque`

## 4. 고수준 제어 (ROS2, 인지 호스트)
`Lite3_ROS` (`ros2-foxy` 브랜치, Ubuntu 20.04)의 `transfer` 패키지가 UDP와 ROS2 토픽을 서로 변환한다.

| 토픽 | 타입 | 방향 |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | 구독. linear.x = 전진(+), linear.y = 왼쪽(+), angular.z = 왼쪽 회전(+) |
| `/simple_cmd` | `transfer_interfaces/MotionSimpleCMD` | 구독. 서기·앉기, 모드 전환처럼 인자가 없는 명령 |
| `/complex_cmd` | `transfer_interfaces/MotionComplexCMD` | 구독. 인자가 있는 명령 |
| `/leg_odom` | `PoseWithCovarianceStamped` | 발행 |
| `/leg_odom2` | `nav_msgs/Odometry` | 발행 |
| `/imu/data` | `sensor_msgs/Imu` | 발행 |
| `/joint_states` | `sensor_msgs/JointState` | 발행 |

- 실행: `source ~/lite_cog_ros2/transfer/install/setup.bash && ros2 launch transfer transfer.launch`
- **`/cmd_vel`이 실제로 반영되려면 앱에서 자동(Auto) 모드로 바꿔야 한다.** 수동 모드로 돌리거나 STOP을 누르면 사람이 제어권을 되찾는다. 이것이 교육용 안전 인터록의 핵심이다(→ 04 문서).
- 커뮤니티에서 정리한 명령 코드(비공식, ⚠️ 확인 필요)
  - `0x21010C03`: 자동 모드 전환
  - `0x21040001`: 하트비트
  - 320 / 325 / 321: 전진 / 횡이동 / 회전 속도
- 시뮬레이터에서는 관절 수준 제어만 재현된다. 내장 보행(`/cmd_vel` 경로)은 **실물에서만 동작**한다.

## 5. 영상
- 앱에 실시간 영상이 나온다. 인지 개발 매뉴얼 V2.2.2에 따르면 **RTSP H.264 720p 스트림**이 있다(URL은 매뉴얼 또는 실물로 확인).
- 깊이 카메라는 인지 호스트에서 직접 접근할 수 있다(장치 종류는 실물로 확인).
