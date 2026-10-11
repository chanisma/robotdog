"""예제 공통: 상위 폴더의 lite3_joint_proto 를 불러오고, --no-view 옵션을 처리한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lite3_joint_proto import JointDog, LEGS, forward_kinematics, inverse_kinematics  # noqa: E402,F401

VIEW = "--no-view" not in sys.argv
