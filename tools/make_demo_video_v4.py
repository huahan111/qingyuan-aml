#!/usr/bin/env python3
"""清源AML 演示视频 v4：截图节奏法（时序精确）。

不使用 Playwright screencast（其帧时间戳与真实捕获时间不符，会导致画面压缩错位）。
改为：asyncio 双任务——
  1) 截图节拍器：每 1/FPS 秒对页面截一帧（时间戳由节拍器保证）；
  2) 操作任务：按配音逐句时间轴执行点击/输入/滚动。
最后 ffmpeg：截图序列(fps) + 7 段人声(+12dB, 延迟 INTRO) 合成 MP4。

用法：python3.14 tools/make_demo_video_v4.py [输出.mp4]
"""
import asyncio
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8983
SEG_DIR = os.path.expanduser("~/Desktop")
SEG_FILES = [os.path.join(SEG_DIR, f"seg{i}.m4a") for i in range(7)]
INTRO = 1.0
FPS = 2.5          # 截图帧率
FRAME_DIR = "/tmp/qy_frames"

SEGMENTS = [
    ("清源AML · 反洗钱智能监测平台（演示系统 · 数据全部合成 · AI 为预生成诊断）",),
    ("演示：一条预警的溯源 —— 判断不是模型说的，是法规写的",),
    ("STR 报告：62 项官方要素罗列齐全 · 第 21、22 项分析为 AI 撰写",),
    ("防篡改审计链：操作层面只增不改 · 哈希一环扣一环 · 完整性校验",),
    ("名单筛查：打分制模糊匹配 · 回溯筛查存量客户 · 正式使用接权威名单库",),
    ("CDD 尽调：国标校验算法 · 数据源后续接 API，现在仅做演示",),
    ("风险评级四维模型实时计算 · 报文报送后续接人行 · 代码开源链接见简介",),
]


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True, **kw)


def audio_duration(path):
    out = sh(f'afinfo "{path}"').stdout
    for line in out.splitlines():
        if "estimated duration" in line:
            return float(line.split(":")[1].strip().split(" ")[0])
    return 6.0


def caption_js(text):
    return f"""(() => {{
      document.getElementById('capbar')?.remove();
      const d = document.createElement('div');
      d.id = 'capbar';
      d.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;'
        + 'background:linear-gradient(90deg,#0F2E4C,#1e4a73);color:#fff;'
        + 'font-size:21px;font-weight:600;padding:13px 26px;text-align:center;'
        + 'box-shadow:0 4px 18px rgba(0,0,0,.35);letter-spacing:.5px;';
      d.textContent = {text!r};
      document.body.appendChild(d);
    }})()"""


MASK_SCROLL = ("(() => { const d = document.querySelector('#reportMask .doc'); "
              "(d || document.scrollingElement).scrollBy(0, 400); })()")

def build_schedule(cum):
    """返回 [(时间秒, 类型, 参数)]，按时间升序。"""
    S = []
    def add(t, kind, arg=""):
        S.append((t, kind, arg))

    for i in range(7):
        add(cum[i], "eval", caption_js(SEGMENTS[i][0]))

    # seg0 工作台全景
    add(cum[0] + 2.0, "move")
    add(cum[0] + 7.0, "eval", "window.scrollBy({top:280})")
    add(cum[0] + 14.0, "eval", "window.scrollBy({top:280})")
    add(cum[0] + 21.0, "eval", "window.scrollBy({top:280})")
    add(cum[0] + 27.0, "siv", "#caseList")
    # seg1 预警溯源
    add(cum[1] + 2.5, "click", ".case-item[data-cid='BLOCK-01']")
    add(cum[1] + 16.5, "click", "#btnDiag")
    add(cum[1] + 25.0, "click", "text=展开溯源")
    add(cum[1] + 34.5, "eval", "window.scrollBy({top:420})")
    add(cum[1] + 38.5, "eval", "window.scrollBy({top:200})")
    # seg2 STR 报告
    add(cum[2] + 2.0, "click", "button:has-text('一键生成 STR 初稿')")
    add(cum[2] + 6.5, "move")
    add(cum[2] + 8.5, "eval", MASK_SCROLL)
    add(cum[2] + 13.5, "eval", MASK_SCROLL)
    add(cum[2] + 18.5, "eval", MASK_SCROLL)
    add(cum[2] + 24.6, "eval", "closeReport()")
    # seg3 审计链
    add(cum[3] + 1.5, "click", ".nav-item[data-page='reports']")
    add(cum[3] + 3.5, "siv", "button:has-text('完整性校验')")
    add(cum[3] + 11.0, "click", "button:has-text('审计查询')")
    add(cum[3] + 12.8, "click", "#auditPanel button:has-text('查询')")
    add(cum[3] + 18.5, "click", "button:has-text('完整性校验')")
    # seg4 名单筛查
    add(cum[4] + 1.5, "click", ".nav-item[data-page='screening']")
    add(cum[4] + 3.5, "type", "#scanInput\x1f组织")
    add(cum[4] + 6.2, "click", "button:has-text('立即筛查')")
    add(cum[4] + 26.5, "siv", "button:has-text('对存量客户执行回溯筛查')")
    add(cum[4] + 27.2, "click", "button:has-text('对存量客户执行回溯筛查')")
    # seg5 CDD
    add(cum[5] + 1.5, "click", ".nav-item[data-page='cdd']")
    add(cum[5] + 3.5, "type", "#cddPerName\x1f赵某")
    add(cum[5] + 4.5, "type", "#cddPerId\x1f999999199303125513")
    add(cum[5] + 19.5, "click", "button.tag:has-text('ZZ供应链')")
    add(cum[5] + 22.5, "click", "button:has-text('发起尽调')")
    # seg6 评级收尾
    add(cum[6] + 1.5, "click", ".nav-item[data-page='rating']")
    add(cum[6] + 9.0, "eval", "window.scrollBy({top:350})")

    S.sort(key=lambda x: x[0])
    return S


async def run(out_path):
    durations = []
    for p in SEG_FILES:
        if not os.path.exists(p):
            print(f"缺少录音文件: {p}"); sys.exit(1)
        durations.append(audio_duration(p))
    cum = [INTRO]
    for d in durations:
        cum.append(cum[-1] + d)
    END = cum[7] + 1.0
    for i, d in enumerate(durations):
        print(f"段{i} 起点 {cum[i]:.1f}s 时长 {d:.1f}s")

    env = dict(os.environ, QINGYUAN_PORT=str(PORT), QINGYUAN_READ_ONLY="0",
               QINGYUAN_RATE_LIMIT="0")
    server = subprocess.Popen([sys.executable, "backend/main.py"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = False
    try:
        import urllib.request
        for _ in range(30):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1)
                break
            except Exception:
                await asyncio.sleep(0.5)
        sh(f'curl -s -X POST http://127.0.0.1:{PORT}/api/admin/reset-demo > /dev/null')

        os.makedirs(FRAME_DIR, exist_ok=True)
        for f in os.listdir(FRAME_DIR):
            os.remove(os.path.join(FRAME_DIR, f))

        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            ctx = await browser.new_context(
                viewport={"width": 1600, "height": 900})
            page = await ctx.new_page()
            await page.goto(f"http://127.0.0.1:{PORT}/")
            await page.mouse.move(800, 450)
            T0 = time.monotonic()
            shot_busy = False

            async def pacer():
                nonlocal shot_busy
                idx = 0
                while True:
                    now = time.monotonic() - T0
                    if now >= END:
                        break
                    await asyncio.sleep(max(0, idx / FPS - now))
                    if not shot_busy:
                        shot_busy = True
                        try:
                            await asyncio.wait_for(
                                page.screenshot(
                                    path=os.path.join(FRAME_DIR, f"f{idx:05d}.jpeg"),
                                    type="jpeg", quality=85),
                                timeout=3.0)
                        except Exception as e:
                            print("截图跳过:", type(e).__name__)
                        finally:
                            shot_busy = False
                    idx += 1

            async def actions():
                for t, kind, arg in build_schedule(cum):
                    delay = T0 + t - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    try:
                        if kind == "click":
                            await page.click(arg, timeout=6000)
                        elif kind == "eval":
                            await page.evaluate(arg)
                        elif kind == "type":
                            sel, txt = arg.split("\x1f")
                            await page.type(sel, txt, delay=180)
                        elif kind == "wheel":
                            await page.mouse.wheel(0, int(arg))
                        elif kind == "move":
                            await page.mouse.move(800, 450)
                        elif kind == "siv":
                            await page.locator(arg).first.scroll_into_view_if_needed()
                        print(f"[{t:6.1f}] {kind} {arg[:30]}")
                    except Exception as e:
                        print(f"[{t:6.1f}] 跳过 {kind}: {type(e).__name__}")

            await asyncio.gather(pacer(), actions())
            await ctx.close()
            await browser.close()
            ok = True
    finally:
        server.terminate()

    n_frames = len([f for f in os.listdir(FRAME_DIR) if f.endswith(".jpeg")])
    print(f"共截取 {n_frames} 帧（{n_frames/FPS:.1f}s，计划 {END:.1f}s）")
    if not ok or n_frames == 0:
        sys.exit(1)

    audio_fc = ("[1:a]volume=12dB[a1];[2:a]volume=12dB[a2];[3:a]volume=12dB[a3];"
                "[4:a]volume=12dB[a4];[5:a]volume=12dB[a5];[6:a]volume=12dB[a6];"
                "[7:a]volume=12dB[a7];"
                "[a1][a2][a3][a4][a5][a6][a7]concat=n=7:v=0:a=1,"
                f"adelay={int(INTRO*1000)}:all=1[a]")
    sh(f'ffmpeg -y -framerate {FPS} -i "{FRAME_DIR}/f%05d.jpeg" '
       f'-i "{SEG_FILES[0]}" -i "{SEG_FILES[1]}" -i "{SEG_FILES[2]}" '
       f'-i "{SEG_FILES[3]}" -i "{SEG_FILES[4]}" -i "{SEG_FILES[5]}" -i "{SEG_FILES[6]}" '
       f'-filter_complex "{audio_fc}" '
       f'-map 0:v -map "[a]" -vf "fps=25,format=yuv420p" '
       f'-c:v libx264 -crf 22 -preset medium -c:a aac -b:a 160k '
       f'-t {END:.2f} "{out_path}"')
    print("已生成 →", os.path.abspath(out_path))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "..", "清源AML_演示视频_人声版_v3.mp4")
    asyncio.run(run(out))
