# 실물 확인 체크리스트 (수령 직후 작성)

문서 값과 실제 값이 다를 수 있으므로 실물에서 확인한 값을 여기에 기록한다. **비밀번호는 이 파일에 적지 말 것**(git에 올라감).

| 항목 | 문서 값 | 실제 값 | 확인 방법 |
|---|---|---|---|
| 일련번호 / MAC | – | | 앱 > General > About Device |
| 앱 버전 | – | | 앱 > General |
| 모션 호스트 펌웨어 (Deeprcs) | – | | `~/jy_exe/scripts/run.sh` 실행 시 출력 |
| Wi-Fi SSID | YSC-JYML-xxxxxx | | 보증서 라벨 |
| 모션 호스트 IP | 192.168.1.120 / 192.168.2.1 | | `ping`, `ssh` |
| 인지 호스트 IP | 192.168.1.103 (추정) | | `nmap -sn 192.168.1.0/24` |
| SSH 계정 | ysc (또는 user, firefly) | | |
| 인지 호스트 OS / JetPack | Xavier NX | | `cat /etc/nv_tegra_release` |
| 인지 호스트 ROS 배포판 | ROS2 Foxy | | `ls /opt/ros` |
| transfer 워크스페이스 경로 | ~/lite_cog_ros2/transfer | | |
| 깊이 카메라 모델 | – | | `lsusb` |
| RTSP URL | – | | 인지 개발 매뉴얼 |
| Pro에서 Auto Mode 지원 여부 | 매뉴얼상 LiDAR 전용 | | 앱 > Settings > Smart Sensing |
| `network.toml` 내용 | target_port 43897, local_port 43893 | | `cat ~/jy_exe/conf/network.toml` |
