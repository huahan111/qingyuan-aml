"""下载并归一化公开制裁名单，生成本项目使用的紧凑名单库。

数据源（均为公开数据，运行时不再联网）：
- 联合国安理会综合名单 UN Consolidated List（XML）
  https://scsanctions.un.org/resources/xml/en/consolidated.xml
- 美国财政部 OFAC SDN（CSV）与别名表（CSV）
  https://www.treasury.gov/ofac/downloads/sdn.csv
  https://www.treasury.gov/ofac/downloads/alt.csv

输出：
- backend/data/sanctions/sanctions.json   条目 + 别名（仓库内自带快照）
- backend/data/sanctions/metadata.json    来源、下载时间、条数、源文件 sha256

用法：
    python3 backend/scripts/fetch_sanctions.py            # 下载 + 生成
    python3 backend/scripts/fetch_sanctions.py --raw-dir /tmp/she lists  # 保留原始文件备查

注意：名单每天都在变。演示用快照足够，生产必须做版本管理与增量回溯筛查
（services/screening.py 的 back_screen 就是这个机制的演示版）。
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

from domain.sanctions.normalize import norm  # noqa: E402

OUT_DIR = os.path.join(BACKEND, "data", "sanctions")
UN_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
OFAC_SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
OFAC_ALT_URL = "https://www.treasury.gov/ofac/downloads/alt.csv"
UA = "QingyuanAML/1.0 (portfolio demo; sanctions list import)"


def _fetch_bytes(url: str) -> bytes:
    """优先 urllib；企业代理/自签证书环境下退回系统 curl（本机常见的 TLS 拦截场景）。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except Exception as e:  # noqa: BLE001 - 任何网络/TLS 问题都尝试 curl
        import shutil
        import subprocess
        if not shutil.which("curl"):
            raise SystemExit(f"下载失败（{e}），且系统没有 curl 可退回：{url}")
        proc = subprocess.run(["curl", "-sSL", "--max-time", "180",
                               "-A", UA, url], capture_output=True)
        if proc.returncode != 0 or not proc.stdout:
            raise SystemExit(f"下载失败：{url}\n{proc.stderr.decode('utf-8', 'replace')[:300]}")
        return proc.stdout


def download(url: str, dest: str) -> dict:
    data = _fetch_bytes(url)
    with open(dest, "wb") as f:
        f.write(data)
    return {"url": url, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _txt(node, tag):
    el = node.find(tag)
    return (el.text or "").strip() if el is not None else ""


def parse_un(path: str):
    root = ET.parse(path).getroot()
    out = []
    for node in root.findall("INDIVIDUALS/INDIVIDUAL"):
        name = " ".join(x for x in (_txt(node, "FIRST_NAME"), _txt(node, "SECOND_NAME"),
                                    _txt(node, "THIRD_NAME"), _txt(node, "FOURTH_NAME")) if x)
        if not name:
            continue
        aliases = [(_txt(a, "ALIAS_NAME")) for a in node.findall("INDIVIDUAL_ALIAS")]
        ctry = [_txt(v, "VALUE") for v in node.findall("NATIONALITY")]
        out.append({"id": "UN-" + (_txt(node, "REFERENCE_NUMBER") or _txt(node, "DATAID")),
                    "n": name, "t": "individual", "src": "UN",
                    "prog": [x for x in [_txt(node, "UN_LIST_TYPE")] if x],
                    "ctry": [c for c in ctry if c], "d": _txt(node, "LISTED_ON"),
                    "a": [a for a in aliases if a]})
    for node in root.findall("ENTITIES/ENTITY"):
        name = _txt(node, "FIRST_NAME")
        if not name:
            continue
        aliases = [(_txt(a, "ALIAS_NAME")) for a in node.findall("ENTITY_ALIAS")]
        ctry = [_txt(v, "VALUE") for v in node.findall("ENTITY_ADDRESS/COUNTRY")]
        out.append({"id": "UN-" + (_txt(node, "REFERENCE_NUMBER") or _txt(node, "DATAID")),
                    "n": name, "t": "entity", "src": "UN",
                    "prog": [x for x in [_txt(node, "UN_LIST_TYPE")] if x],
                    "ctry": [c for c in ctry if c], "d": _txt(node, "LISTED_ON"),
                    "a": [a for a in aliases if a]})
    return out


def _programs(raw: str):
    raw = (raw or "").replace("[", " ").replace("]", " ")
    parts = [p.strip() for p in raw.split() if p.strip() and p.strip() not in ("-0-", "-")]
    # OFAC 形如 "FTO] [SDGT"，去括号后按词切；保留去重后的原始顺序
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def parse_ofac(sdn_path: str, alt_path: str):
    alts = {}
    with open(alt_path, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 4:
                continue
            num, _alt_num, kind, alt_name = (row[0].strip(), row[1].strip(),
                                             row[2].strip().lower(), row[3].strip())
            if kind in ("aka", "fka", "nka") and alt_name:
                alts.setdefault(num, []).append(alt_name)

    out, seen = [], set()
    with open(sdn_path, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 4:
                continue
            num, name, typ, prog = (row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip())
            if not name or num in seen:
                continue
            seen.add(num)
            t = typ if typ in ("individual", "entity", "vessel", "aircraft") else "entity"
            out.append({"id": "OFAC-" + num, "n": name, "t": t, "src": "OFAC",
                        "prog": _programs(prog), "ctry": [], "d": "",
                        "a": alts.get(num, [])})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default="", help="保留原始下载文件到指定目录（默认用临时目录并删除）")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = args.raw_dir or tempfile.mkdtemp(prefix="sanctions_")
    os.makedirs(tmp, exist_ok=True)

    print("下载联合国综合名单…")
    un_meta = download(UN_URL, os.path.join(tmp, "un_consolidated.xml"))
    print(f"  {un_meta['bytes'] / 1024:.0f} KB")
    print("下载 OFAC SDN 与别名表…")
    sdn_meta = download(OFAC_SDN_URL, os.path.join(tmp, "sdn.csv"))
    alt_meta = download(OFAC_ALT_URL, os.path.join(tmp, "alt.csv"))
    print(f"  {sdn_meta['bytes'] / 1024:.0f} KB / {alt_meta['bytes'] / 1024:.0f} KB")

    un_entries = parse_un(os.path.join(tmp, "un_consolidated.xml"))
    ofac_entries = parse_ofac(os.path.join(tmp, "sdn.csv"), os.path.join(tmp, "alt.csv"))
    entries = un_entries + ofac_entries

    # 去重：同源同名视为重复（OFAC 里同一主体有多条 ent_num）
    dedup, seen = [], set()
    for e in entries:
        k = (e["src"], norm(e["n"]))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(e)
    entries = dedup
    entries.sort(key=lambda e: (e["src"] != "UN", e["id"]))

    zh_path = os.path.join(OUT_DIR, "zh_aliases.json")
    zh_count = 0
    if os.path.isfile(zh_path):
        with open(zh_path, encoding="utf-8") as f:
            zh_count = sum(len(v) for v in json.load(f).get("aliases", {}).values())

    payload = {"_meta": {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "schema": "qingyuan-sanctions/1"},
               "entries": entries}
    list_path = os.path.join(OUT_DIR, "sanctions.json")
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    total_alias = sum(len(e["a"]) for e in entries)
    meta = {
        "generated_at": payload["_meta"]["generated_at"],
        "total_entries": len(entries),
        "total_aliases": total_alias,
        "zh_alias_count": zh_count,
        "sources": [
            {"name": "联合国安理会综合名单（UN Consolidated List）", "entries": len(un_entries), **un_meta},
            {"name": "OFAC SDN（含别名表 alt.csv）", "entries": len(ofac_entries),
             **{k: v for k, v in sdn_meta.items()},
             "alt_csv": {"url": alt_meta["url"], "sha256": alt_meta["sha256"]}},
        ],
        "file_size": os.path.getsize(list_path),
        "license_note": "联合国名单与 OFAC 名单均为公开数据，可自由查阅转载；"
                        "OFAC 数据为美国政府公开出版物。本仓库仅存派生快照，不主张任何权利。",
        "refresh": "python3 backend/scripts/fetch_sanctions.py（建议每次演示前刷新一次）",
    }
    with open(os.path.join(OUT_DIR, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"完成：{len(entries)} 条（UN {len(un_entries)} / OFAC {len(ofac_entries)}），"
          f"别名 {total_alias} 个，中译名 {zh_count} 个，文件 {meta['file_size'] / 1024:.0f} KB")
    print(f"写入：{list_path}")


if __name__ == "__main__":
    main()
