"""演示环境安全开关：只读模式用于公开部署，禁止一切写接口。"""
import os

_TRUE = {"1", "true", "yes", "on"}


def is_read_only():
    return os.getenv("QINGYUAN_READ_ONLY", "0").strip().lower() in _TRUE
