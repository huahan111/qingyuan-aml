"""运行全部测试：相似案例 + 案例联动 + API 契约 + 审计链 + E2E + 授权状态机。

浏览器类测试（E2E / 授权状态机）依赖 playwright；未安装时自动跳过并提示，
不会让整套测试崩在 ModuleNotFoundError 上（依赖安装见 requirements-dev.txt）。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPTS = (
    ("tests/case_similarity.py", False),
    ("tests/case_linkage.py", False),
    ("tests/audit_chain.py", False),
    ("tests/auth.py", False),
    ("tests/api_contract.py", False),
    ("tests/e2e_smoke.py", True),          # 需要 playwright + chromium
    ("tests/auth_state_machine.py", True),  # 需要 playwright + chromium
)

try:
    import playwright  # noqa: F401
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

skipped = []
for script, needs_browser in SCRIPTS:
    print(f"\n=== {script} ===")
    if needs_browser and not HAS_PLAYWRIGHT:
        print(f"SKIP {script}：未安装 playwright（pip install -r requirements-dev.txt "
              f"&& python -m playwright install chromium）")
        skipped.append(script)
        continue
    r = subprocess.run([sys.executable, script], cwd=ROOT)
    if r.returncode != 0:
        sys.exit(r.returncode)

print("\n全部测试通过：相似案例 + 案例联动 + 审计链 + 鉴权 + API 契约 + E2E + 授权状态机")
if skipped:
    print(f"（本次跳过浏览器测试 {len(skipped)} 项：{'、'.join(skipped)}）")
