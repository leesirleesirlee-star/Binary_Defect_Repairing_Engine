#!/bin/sh
# 双击打开固定地址的 BinaryRepair GUI（新版控制台）。
# 需要时自动启动 8124 新版控制台和 8125 旧版界面，然后打开：
#   http://127.0.0.1:8124/welcome
set -eu

SELF="$0"
while [ -L "$SELF" ]; do
  link="$(readlink "$SELF")"
  case "$link" in
    /*) SELF="$link" ;;
    *) SELF="$(dirname "$SELF")/$link" ;;
  esac
done
ROOT="$(cd "$(dirname "$SELF")" && pwd -P)"

exec "$ROOT/scripts/open-gui.sh"
