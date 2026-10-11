# third_party

DeepRoboticsLab 공식 저장소를 받아 두는 곳이다. 이 폴더의 내용은 git으로 추적하지 않는다.

```bash
bash scripts/clone_upstream.sh        # 핵심 7개 저장소
bash scripts/clone_upstream.sh --all  # 응용·구형 저장소까지
```

공식 저장소는 직접 수정하지 않는다. 바꿀 내용은 이 프로젝트의 `sim/`, `deploy/`, `edu/` 쪽에 래퍼나 패치로 둔다.
