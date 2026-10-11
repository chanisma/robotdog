# CLAUDE.md

DEEP Robotics Lite3 Pro 4족 로봇을 활용한 교육·연구 프로젝트. 문서는 한국어로 작성한다.

대상 학습자는 **고등학생이고 아주 기초적인 Python만 배운 상태**다. AI보다 기본 조작을 먼저 가르친다. 학생이 쓰는 코드는 ROS2를 감춘 `lite3_edu` 라이브러리(`docs/plan/edu_python_api.md`)로만 다룬다.

- 로봇에 관한 사실은 `docs/knowledge/`에 있다. 새로 알게 된 사실은 출처와 함께 이곳에 추가하고, 확인되지 않은 값에는 ⚠️를 붙인다.
- 공식 저장소는 `third_party/`에 있고 직접 수정하지 않는다(`scripts/clone_upstream.sh` 참고).
- 실물 로봇에 명령을 보내는 코드는 `docs/knowledge/05_safety.md`를 따른다: 저속부터 시작하고, 저수준 제어는 호이스트에 매단 상태에서 하며, E-STOP을 확보한다.
- 비밀번호와 API 키는 커밋하지 않는다(`.env` 사용).
