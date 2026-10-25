#!/usr/bin/env python3
"""一键生成清源AML 演示视频（macOS）：Playwright 录屏 + say 中文配音 + ffmpeg 合成。

用法：
  python3 tools/make_demo_video.py [输出.mp4]        # 默认 ../清源AML_演示视频_自动生成版.mp4
依赖：playwright（chromium 已装）、ffmpeg、macOS 自带 say/afinfo（zh_CN 语音）。
说明：自动版用于快速出片；追求人声时按《清源AML_演示视频脚本_3分钟版.md》自行录制，
      本脚本的分镜与停顿与该脚本一致，可直接替换配音。
"""
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8981
VOICE = "Eddy (中文（中国大陆）)"   # `say -v '?' | grep zh_CN` 查看可选；须带全名否则落到英文同名语音
RATE = 205

SEGMENTS = [
    ("清源AML · 反洗钱智能监测平台（演示系统 · 数据全部脱敏合成）",
     "清源反洗钱智能监测平台。数据全部脱敏合成，AI使用预生成诊断，报文层未接人行专线。"
     "它是演示系统，但每一步都是真后端真代码，百余项自动化测试全绿。"),
    ("核心：一条预警的四层溯源 —— 判断不是模型说的，是法规写的",
     "点开预警，规则引擎命中R002：八笔现金存入全部紧贴五万申报线，典型分拆规避。"
     "溯源面板四层下钻：规则逻辑、三号令原文、官方类型识别点、处罚事由。判断不是模型说的，是法规写的。"),
    ("STR 报告：62 项要素逐项标来源 · AI 只写 2 项 · 系统不装懂",
     "一键生成可疑交易报告：六十二项官方要素逐项标来源，AI只写第二十一、二十二两项分析。"
     "没接官方代码集的特征代码就留空——系统不装懂。"),
    ("防篡改审计链：SHA256 哈希链 · 服务器毫秒时间戳 · 改库文件也能检出",
     "每一次操作都写入防篡改审计链：只增不改，触发器拒绝改删，哈希链覆盖服务器毫秒时间戳。"
     "点完整性校验，全链重放——直接改数据库文件也能检出。"),
    ("名单筛查 v2：打分制模糊匹配 + 回溯筛查存量客户",
     "名单筛查是打分制模糊匹配：错别字、缺前缀只给疑似、转人工，不再误报命中。"
     "名单更新后一键回溯筛查存量客户——这是监管检查必看的环节。"),
    ("CDD 尽调窗口：国标校验位算法 · 未接入的数据源如实说未接入",
     "尽调窗口能真查：统一社会信用代码走国标校验位算法，示例号一键直查，"
     "风险标签与受益所有人一目了然。数据源没接，就如实说没接。"),
    ("风险评级四维模型实时计算 · 在线只读演示与开源代码链接见简介",
     "客户风险评级四维模型实时计算，预警结果动态回写，名单命中一票升级。"
     "在线只读演示与开源代码链接，见本页简介。"),
]


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True, **kw)


def make_narration_audio(text, path):
    txt = path + ".txt"
    with open(txt, "w", encoding="utf-8") as f:
        f.write(text)
    sh(f'say -v {VOICE!r} -r {RATE} -f "{txt}" -o "{path}"')


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


def main(out_path):
    tmp = tempfile.TemporaryDirectory()
    # 1) 配音（逐段，便于对齐停顿）
    durations = []
    for i, (_, narration) in enumerate(SEGMENTS):
        aiff = os.path.join(tmp.name, f"seg{i}.aiff")
        make_narration_audio(narration, aiff)
        durations.append(audio_duration(aiff))
        print(f"配音段{i}：{durations[-1]:.1f}s")
    list_file = os.path.join(tmp.name, "list.txt")
    with open(list_file, "w") as f:
        for i in range(len(SEGMENTS)):
            f.write(f"file 'seg{i}.aiff'\n")
    narration = os.path.join(tmp.name, "narration.aiff")
    sh(f'ffmpeg -y -f concat -safe 0 -i "{list_file}" -c copy "{narration}"')

    # 2) 起本地服务（可写，演示完整报送链路）并清场
    env = dict(os.environ, QINGYUAN_PORT=str(PORT), QINGYUAN_READ_ONLY="0",
               QINGYUAN_RATE_LIMIT="0")
    server = subprocess.Popen([sys.executable, "backend/main.py"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            try:
                import urllib.request
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        sh(f'curl -s -X POST http://127.0.0.1:{PORT}/api/admin/reset-demo > /dev/null')

        # 3) 录屏驱动
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(
                viewport={"width": 1600, "height": 900},
                record_video_dir=tmp.name, record_video_size={"width": 1600, "height": 900})
            page = ctx.new_page()
            page.goto(f"http://127.0.0.1:{PORT}/")
            page.wait_for_timeout(1500)

            def hold(sec):
                page.wait_for_timeout(int(sec * 1000))

            def cap(i):
                page.evaluate(caption_js(SEGMENTS[i][0]))

            # 精确选择器（text= 会命中标题等子串文本，导致点错元素）
            def click_sel(sel, sec=0.8, wait_for=""):
                try:
                    if wait_for:
                        page.wait_for_selector(wait_for, timeout=8000)
                    page.click(sel, timeout=6000)
                    hold(sec)
                except Exception as e:
                    print("点击跳过:", sel, type(e).__name__)

            # S0 工作台全景
            cap(0); hold(durations[0] + 0.6)
            # S1 主案研判 + 溯源（先点研判按钮，等结果区出现后再点溯源）
            cap(1)
            click_sel(".case-item[data-cid='BLOCK-01']", 1.2)
            click_sel("#btnDiag", 0.8)
            try:
                page.wait_for_selector("text=展开溯源", timeout=10000)
                hold(1.2)
            except Exception:
                print("研判结果区未出现")
            click_sel("text=展开溯源", 2.0)
            hold(max(0, durations[1] - 5.0))
            # S2 STR（生成按钮在研判结果区；看完后关闭报告弹层，否则遮罩挡住导航）
            cap(2)
            click_sel("button:has-text('一键生成 STR 初稿')", 1.5)
            try:
                for _ in range(8):
                    page.mouse.wheel(0, 320); hold(0.35)
            except Exception:
                pass
            hold(max(0, durations[2] - 5.0))
            page.evaluate("closeReport()"); hold(0.8)
            # S3 审计链
            cap(3)
            click_sel(".nav-item[data-page='reports']", 1.2)
            click_sel("button:has-text('完整性校验')", 2.0)
            hold(max(0, durations[3] - 3.2))
            # S4 名单筛查 + 回溯
            cap(4)
            click_sel(".nav-item[data-page='screening']", 1.0)
            click_sel("button:has-text('回溯筛查')", 2.2)
            hold(max(0, durations[4] - 3.2))
            # S5 CDD（示例号一键直查）
            cap(5)
            click_sel(".nav-item[data-page='cdd']", 1.0)
            click_sel("button.tag:has-text('ZZ供应链')", 2.2)
            hold(max(0, durations[5] - 3.2))
            # S6 评级 + 收尾
            cap(6)
            click_sel(".nav-item[data-page='rating']", 1.5)
            hold(durations[6] + 1.2)

            ctx.close(); browser.close()
            video = page.video.path()
    finally:
        server.terminate()

    # 4) 合成
    out_path = out_path or os.path.join(ROOT, "..", "清源AML_演示视频_自动生成版.mp4")
    sh(f'ffmpeg -y -i "{video}" -i "{narration}" -c:v libx264 -crf 23 -preset medium '
       f'-c:a aac -b:a 128k -pix_fmt yuv420p "{out_path}"')
    print("已生成 →", os.path.abspath(out_path))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
