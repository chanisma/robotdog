#!/usr/bin/env bash
# DeepRoboticsLab 공식 저장소를 third_party/ 에 클론한다 (git 추적 제외).
# 사용법: bash scripts/clone_upstream.sh [--all]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/third_party"
mkdir -p "$DEST"

CORE=(
  sdk_deploy
  Lite3_rl_deploy
  rl_training
  deep_robotics_model
  Lite3_ROS
  gamepad
  Robot_Training_Cases
)
EXTRA=(
  Lite3_LLM
  Lite3_Navigation
  Lite3_SLAM
  Lite3_Track
  Lite3_VMC
  Lite3_MotionSDK
)

repos=("${CORE[@]}")
[[ "${1:-}" == "--all" ]] && repos+=("${EXTRA[@]}")

for r in "${repos[@]}"; do
  if [[ -d "$DEST/$r/.git" ]]; then
    echo "[update] $r"
    git -C "$DEST/$r" pull --ff-only
    git -C "$DEST/$r" submodule update --init --recursive
  else
    echo "[clone]  $r"
    git clone --recurse-submodules "https://github.com/DeepRoboticsLab/$r.git" "$DEST/$r"
  fi
done
