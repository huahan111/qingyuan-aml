"""演示环境安全开关：默认只读（fail-closed），公开/托管部署零配置安全。

直启 `python3 backend/main.py`（容器、托管平台）默认只读——平台通常只注入 PORT、
无法自定义环境变量，靠默认值保证公开实例不可写。
本机交互演示需要写台账时：用 run.sh（默认可写且仅监听 127.0.0.1），
或显式 `QINGYUAN_READ_ONLY=0 python3 backend/main.py`。
"""
import os

_TRUE = {"1", "true", "yes", "on"}


def is_read_only():
    return os.getenv("QINGYUAN_READ_ONLY", "1").strip().lower() in _TRUE
