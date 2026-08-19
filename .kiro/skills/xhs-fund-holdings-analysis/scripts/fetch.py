# -*- coding: utf-8 -*-
"""
基金 5 页持仓笔记 · 数据抓取脚本（自包含 / 单文件）

为本 skill (xhs-fund-holdings-analysis) 量身定制。复制本文件到
{topic_folder}/fetch.py，改顶部 FUND_CODE，运行即可：

    python fetch.py

会产出 data.json，字段直接对应 5 页所需：
- basic       → P1 封面 + P3 任职数据
- manager     → P3 经理名片 + 头像
- holdings    → P2 持仓演化（近 4 季 Top10）
- analysis    → P4 交易习惯（稳定度 / 集中度 / 区域 / 换仓）
                P5 推测素材（new_in / new_out / add / reduce）

⚠ 强制约束（违反任一条视为任务失败）：
1. 禁止伪造任何字段。抓不到就标 null + _warnings，不准瞎填。
2. 禁止用 LLM "常识" 补全字段（如「这只基金大概 50 亿」）。只信抓回来的 HTML。
3. 头像必须真实抓取，不许用 emoji / 占位符。
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime

import requests

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 配置：复制脚本后只改这一行
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FUND_CODE = "016665"  # ← 改这里

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 反爬基础（HEADERS / sleep / get / strip_tags）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "http://fund.eastmoney.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

FUND_URL = "http://fund.eastmoney.com/{code}.html"
MANAGER_URL = "http://fundf10.eastmoney.com/jjjl_{code}.html"
HOLDING_URL = (
    "http://fundf10.eastmoney.com/FundArchivesDatas.aspx"
    "?type=jjcc&code={code}&topline=10&year={year}&month=&rt=0.1"
)


def sleep(lo: float = 0.5, hi: float = 2.0) -> None:
    time.sleep(random.uniform(lo, hi))


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def get(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.encoding = "utf-8"
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} - {url}")
    return resp.text


def get_with_retry(url: str, retries: int = 2) -> str | None:
    for i in range(retries + 1):
        try:
            return get(url)
        except Exception as e:
            print(f"  ! 请求失败 ({i + 1}/{retries + 1}) {url} - {e}")
            sleep()
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 解析：基金主页
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def parse_main(html: str) -> dict:
    info: dict = {}

    m = re.search(r"<title>(.*?)\((\d{6})\)", html)
    if m:
        info["name"] = m.group(1).strip()
        info["code"] = m.group(2).strip()

    info_block_match = re.search(
        r'<div class="infoOfFund">(.*?)基金评级', html, re.DOTALL
    )
    if info_block_match:
        block = strip_tags(info_block_match.group(0))
        m = re.search(r"类型[：:]\s*([^\s|]+)\s*(?:&nbsp;|\s)*\|\s*(?:&nbsp;|\s)*([^\s]+风险)", block)
        if m:
            info["type"] = m.group(1)
            info["risk"] = m.group(2)
        m = re.search(r"规模\s*[：:]\s*([\d.,]+亿元)", block)
        if m:
            info["scale"] = m.group(1)
        m = re.search(r"基金经理[：:]\s*([\u4e00-\u9fa5A-Za-z]+)", block)
        if m:
            info["manager_name"] = m.group(1)
        m = re.search(r"成\s*立\s*日\s*[：:]\s*([\d-]+)", block)
        if m:
            info["found_date"] = m.group(1)
        m = re.search(r"管\s*理\s*人\s*[：:]\s*([\u4e00-\u9fa5]+)", block)
        if m:
            info["company"] = m.group(1)

    m = re.search(r'class="fix_dwjz[^"]*"[^>]*>([\d.]+)<', html)
    if m:
        info["nav"] = m.group(1)
    m = re.search(r'class="fix_date">\((\d{2}-\d{2})', html)
    if m:
        info["nav_date"] = m.group(1)

    for key, label in [
        ("return_1m", "近1月"), ("return_3m", "近3月"),
        ("return_6m", "近6月"), ("return_1y", "近1年"),
        ("return_3y", "近3年"), ("return_sl", "成立来"),
    ]:
        m = re.search(
            re.escape(label) + r"[：:]\s*</span>\s*<span[^>]*>([-\d.]+)%?</span>",
            html,
        )
        if m:
            info[key] = m.group(1) + "%"

    return info


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 解析：基金经理（含头像）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def parse_manager(html: str) -> dict:
    info: dict = {}

    # 任职区间表
    all_tables = re.findall(
        r'<table[^>]*class="[^"]*jloff[^"]*"[^>]*>(.+?)</table>',
        html, re.DOTALL,
    )
    tenures: list[dict] = []
    if all_tables:
        first = all_tables[0]
        for tr in re.findall(r"<tr[^>]*>(.+?)</tr>", first, re.DOTALL):
            if "<th" in tr:
                continue
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
            if len(tds) < 5:
                continue
            start = strip_tags(tds[0])
            end = strip_tags(tds[1])
            managers = re.findall(r">([^<>]+)</a>", tds[2]) or [strip_tags(tds[2])]
            tenures.append({
                "start": start, "end": end,
                "period": f"{start} ~ {end}",
                "managers": managers,
                "days": strip_tags(tds[3]),
                "return": strip_tags(tds[4]),
            })
    info["tenures"] = tenures
    info["current"] = next((t for t in tenures if "至今" in t["end"]), None)

    # 头像（必须真实抓取）
    avatar = ""
    ma = re.search(r'<div[^>]*class="[^"]*pic[^"]*"[^>]*>.*?<img[^>]+src="([^"]+)"', html, re.DOTALL)
    if ma:
        avatar = ma.group(1)
    if not avatar:
        ma = re.search(r'<div class="jl_intro">.*?<img[^>]+src="([^"]+)"', html, re.DOTALL)
        if ma:
            avatar = ma.group(1)
    if avatar.startswith("//"):
        avatar = "https:" + avatar

    # 简介块
    profiles: list[dict] = []
    for m in re.finditer(r'<div class="jl_intro">(.+?)</div>\s*</div>\s*</div>', html, re.DOTALL):
        block = m.group(1)
        name_m = re.search(r"<strong>姓名：</strong>\s*<a[^>]*>([^<]+)</a>", block) \
                 or re.search(r"<strong>姓名：</strong>\s*([^<]+)", block)
        start_m = re.search(r"<strong>上任日期：</strong>\s*([\d-]+)", block)
        bio = ""
        for p in re.findall(r"<p[^>]*>(.*?)</p>", block, re.DOTALL):
            text = strip_tags(p)
            if text.startswith("姓名") or text.startswith("上任日期"):
                continue
            if "查看" in text and len(text) < 10:
                continue
            if len(text) > 20:
                bio = text
                break
        profiles.append({
            "name": name_m.group(1).strip() if name_m else "",
            "avatar": avatar,
            "appoint_date": start_m.group(1) if start_m else "",
            "bio": bio,
        })
    info["profiles"] = profiles
    return info


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 解析：季度持仓
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def parse_holdings_response(text: str) -> list[dict]:
    m = re.search(r"content:\"(.+?)\",arryear:", text, re.DOTALL)
    if not m:
        return []
    content = m.group(1).replace('\\"', '"').replace("\\/", "/").replace("\\'", "'")

    quarters: list[dict] = []
    boxes = re.findall(r"<div class='box'>(.+?)(?=<div class='box'>|$)", content, re.DOTALL) or [content]
    for box in boxes:
        tm = re.search(r"(\d{4}年\s*\d季度)", box)
        if not tm:
            continue
        quarter = tm.group(1).replace(" ", "")

        tbody = re.search(r"<tbody>(.+?)</tbody>", box, re.DOTALL)
        if not tbody:
            continue
        stocks: list[dict] = []
        for tr in re.findall(r"<tr[^>]*>(.+?)</tr>", tbody.group(1), re.DOTALL):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
            if len(tds) < 5:
                continue
            raw = [strip_tags(td) for td in tds]
            if not raw[0].isdigit():
                continue
            name_m = re.search(r">([^<>]+)</a>", tds[2])
            name = name_m.group(1).strip() if name_m else raw[2]
            pct = next((v for v in raw if v.endswith("%")), "")
            stocks.append({
                "code": raw[1], "name": name, "pct": pct,
                "shares": raw[-2] if len(raw) >= 2 else "",
                "value": raw[-1] if len(raw) >= 1 else "",
            })
        if stocks:
            quarters.append({"quarter": quarter, "stocks": stocks})
    return quarters


def fetch_holdings(code: str, years: list[int]) -> list[dict]:
    all_q: list[dict] = []
    seen = set()
    for y in years:
        text = get_with_retry(HOLDING_URL.format(code=code, year=y))
        if text is None:
            continue
        for q in parse_holdings_response(text):
            if q["quarter"] not in seen:
                seen.add(q["quarter"])
                all_q.append(q)
        sleep(1.0, 2.0)

    def key(q):
        m = re.match(r"(\d{4})年(\d)季度", q["quarter"])
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)

    all_q.sort(key=key, reverse=True)
    return all_q


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 派生分析（仅基于真实持仓计算 · 5 页所需）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _pct_to_float(s: str) -> float:
    try:
        return float(s.replace("%", "").replace(",", "").strip())
    except Exception:
        return 0.0


def analyze(quarters: list[dict]) -> dict:
    """
    产出 P4 / P5 所需的派生字段：
    - core_stocks / stability_pct  → P2 金色高亮、P4 稳定度卡
    - movements (new_in / new_out / add / reduce) → P2 蓝色高亮、P4 换仓卡、P5 信号
    - concentration (top3 / top10 × 4 季) → P4 集中度卡 + 趋势条
    - region_mix → P4 候选卡：A 股 vs 海外 / 全球地理分布
    """
    if not quarters:
        return {}

    recent = quarters[:4]
    sets = [{s["code"] for s in q["stocks"]} for q in recent]
    core = set.intersection(*sets) if len(sets) >= 2 else sets[0]
    top_n = len(recent[0]["stocks"]) if recent else 10
    stability = round(len(core) / max(top_n, 1) * 100, 1)

    movements = {"new_in": [], "new_out": [], "add": [], "reduce": [], "hold": []}
    if len(recent) >= 2:
        latest = {s["code"]: s for s in recent[0]["stocks"]}
        prev = {s["code"]: s for s in recent[1]["stocks"]}
        for code, s in latest.items():
            if code not in prev:
                movements["new_in"].append({"code": code, "name": s["name"], "pct": s["pct"]})
            else:
                diff = _pct_to_float(s["pct"]) - _pct_to_float(prev[code]["pct"])
                bucket = "add" if diff >= 0.3 else "reduce" if diff <= -0.3 else "hold"
                row = {"code": code, "name": s["name"], "pct": s["pct"]}
                if bucket != "hold":
                    row["diff"] = round(diff, 2)
                movements[bucket].append(row)
        for code, s in prev.items():
            if code not in latest:
                movements["new_out"].append({"code": code, "name": s["name"], "pct": s["pct"]})

    def sum_top(q, n):
        return round(sum(_pct_to_float(s["pct"]) for s in q["stocks"][:n]), 2)

    concentration = [
        {"quarter": q["quarter"], "top3": sum_top(q, 3), "top10": sum_top(q, 10)}
        for q in recent
    ]

    # 地理分布：A 股 / 海外（粗粒度，全球型基金可在 HTML 里再拆国家）
    region: dict[str, float] = {}
    if recent:
        buckets = {"A股": 0.0, "海外": 0.0}
        for s in recent[0]["stocks"]:
            buckets["A股" if s["code"].isdigit() else "海外"] += _pct_to_float(s["pct"])
        region = {k: round(v, 2) for k, v in buckets.items()}

    return {
        "core_stocks": sorted(core),
        "core_count": len(core),
        "stability_pct": stability,
        "movements": movements,
        "concentration": concentration,
        "region_mix": region,
        "latest_top5": recent[0]["stocks"][:5] if recent else [],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 关键字段自检（不通过仅告警，不阻断）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def assert_required(data: dict, keys: list[str], label: str = "") -> list[str]:
    missing = [k for k in keys if not data.get(k)]
    if missing:
        print(f"  ! [{label}] 缺失字段: {missing}")
    return missing


def write_json(target_path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"完成 → {target_path}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main() -> None:
    out: dict = {"code": FUND_CODE, "_warnings": []}

    print(f"[1/3] 抓取基金主页 {FUND_CODE}")
    html = get_with_retry(FUND_URL.format(code=FUND_CODE))
    out["basic"] = parse_main(html) if html else {}
    if not html:
        out["_warnings"].append("main_page_failed")
    sleep(1.0, 2.0)

    print("[2/3] 抓取基金经理页（含头像）")
    html = get_with_retry(MANAGER_URL.format(code=FUND_CODE))
    out["manager"] = parse_manager(html) if html else {}
    if not html:
        out["_warnings"].append("manager_page_failed")
    sleep(1.0, 2.0)

    print("[3/3] 抓取近 4 年持仓")
    cy = datetime.now().year
    out["holdings"] = fetch_holdings(FUND_CODE, [cy, cy - 1, cy - 2, cy - 3])
    if not out["holdings"]:
        out["_warnings"].append("holdings_empty")

    out["analysis"] = analyze(out["holdings"])
    out["update_date"] = time.strftime("%Y-%m-%d")

    # 关键字段缺失告警（不阻断）
    missing = assert_required(
        out.get("basic", {}),
        ["name", "manager_name"],
        label="basic"
    )
    if missing:
        out["_warnings"].append({"basic_missing": missing})

    if not out.get("manager", {}).get("profiles"):
        out["_warnings"].append("manager_profile_missing")
    elif not out["manager"]["profiles"][0].get("avatar"):
        out["_warnings"].append("avatar_missing")

    target = os.path.join(os.path.dirname(__file__), "data.json")
    write_json(target, out)

    # 控制台抽检摘要
    print(f"\n— 抽检 —")
    print(f"  基金: {out['basic'].get('name')} {out['code']}")
    print(f"  经理: {out['basic'].get('manager_name')}")
    print(f"  规模: {out['basic'].get('scale')}")
    print(f"  近1年: {out['basic'].get('return_1y')}  近3年: {out['basic'].get('return_3y')}")
    print(f"  持仓季度: {len(out['holdings'])} 季")
    if out["holdings"]:
        print(f"    最新: {out['holdings'][0]['quarter']} · {len(out['holdings'][0]['stocks'])} 只")
    if out.get("manager", {}).get("profiles"):
        for p in out["manager"]["profiles"]:
            print(f"  经理头像: {p.get('avatar') or '— 缺失 —'}")
    a = out.get("analysis", {})
    if a:
        print(f"  核心稳定度: {a.get('stability_pct')}% (core={a.get('core_count')})")
        print(f"  最新换仓: 新进 {len(a['movements']['new_in'])}  退出 {len(a['movements']['new_out'])}")
    if out["_warnings"]:
        print(f"  ⚠ Warnings: {out['_warnings']}")


if __name__ == "__main__":
    main()
