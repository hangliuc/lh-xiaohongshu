# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import random
import re
import time

import requests

FUND_CODE = "014002"

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


def _get(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.encoding = "utf-8"
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} - {url}")
    return resp.text


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


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
        block = _strip_tags(info_block_match.group(0))
        m = re.search(r"类型[：:]\s*([^\s|]+)\s*(?:&nbsp;|\s)*\|\s*(?:&nbsp;|\s)*([^\s]+风险)", block)
        if m:
            info["type"] = m.group(1)
            info["risk"] = m.group(2)
        else:
            m = re.search(r"类型[：:]\s*([A-Za-z\u4e00-\u9fa5\-]+)", block)
            if m:
                info["type"] = m.group(1)
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
        ("return_1m", "近1月"),
        ("return_3m", "近3月"),
        ("return_6m", "近6月"),
        ("return_1y", "近1年"),
        ("return_3y", "近3年"),
        ("return_sl", "成立来"),
    ]:
        m = re.search(
            re.escape(label) + r"[：:]\s*</span>\s*<span[^>]*>([-\d.]+)%?</span>",
            html,
        )
        if m:
            info[key] = m.group(1) + "%"

    m = re.search(r"成立来[：:][^<]*<[^>]*>([-\d.]+)%", html)
    if m and "return_sl" not in info:
        info["return_sl"] = m.group(1) + "%"

    return info


def parse_manager(html: str) -> dict:
    info: dict = {}

    all_tables = re.findall(
        r'<table[^>]*class="[^"]*jloff[^"]*"[^>]*>(.+?)</table>',
        html, re.DOTALL,
    )

    tenures: list[dict] = []
    if all_tables:
        first = all_tables[0]
        tr_list = re.findall(r"<tr[^>]*>(.+?)</tr>", first, re.DOTALL)
        for tr in tr_list:
            if "<th" in tr:
                continue
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
            if len(tds) < 5:
                continue
            start = _strip_tags(tds[0])
            end = _strip_tags(tds[1])
            manager_html = tds[2]
            managers = re.findall(r">([^<>]+)</a>", manager_html)
            if not managers:
                managers = [_strip_tags(manager_html)]
            days = _strip_tags(tds[3])
            ret = _strip_tags(tds[4])
            tenures.append({
                "start": start,
                "end": end,
                "period": f"{start} ~ {end}",
                "managers": managers,
                "days": days,
                "return": ret,
            })
    info["tenures"] = tenures

    current = None
    for t in tenures:
        if "至今" in t["end"]:
            current = t
            break
    if current:
        info["current"] = current

    avatar = ""
    ma_all = re.search(r'<div[^>]*class="[^"]*pic[^"]*"[^>]*>.*?<img[^>]+src="([^"]+)"', html, re.DOTALL)
    if ma_all:
        avatar = ma_all.group(1)
    if not avatar:
        ma_jl = re.search(r'<div class="jl_intro">.*?<img[^>]+src="([^"]+)"', html, re.DOTALL)
        if ma_jl:
            avatar = ma_jl.group(1)
    if avatar and avatar.startswith('//'):
        avatar = 'https:' + avatar

    profiles: list[dict] = []
    for m in re.finditer(
        r'<div class="jl_intro">(.+?)</div>\s*</div>\s*</div>',
        html, re.DOTALL,
    ):
        block = m.group(1)
        if not avatar:
            ma = re.search(r'<img[^>]+src="([^"]+)"', block)
            if ma:
                avatar = ma.group(1)
                if avatar.startswith('//'):
                    avatar = 'https:' + avatar
        name = ""
        mn = re.search(r"<strong>姓名：</strong>\s*<a[^>]*>([^<]+)</a>", block)
        if not mn:
            mn = re.search(r"<strong>姓名：</strong>\s*([^<]+)", block)
        if mn:
            name = mn.group(1).strip()
        start = ""
        ms = re.search(r"<strong>上任日期：</strong>\s*([\d-]+)", block)
        if ms:
            start = ms.group(1)
        paras = re.findall(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
        bio = ""
        for p in paras:
            text = _strip_tags(p)
            if name and text.startswith("姓名"):
                continue
            if text.startswith("上任日期"):
                continue
            if "查看" in text and len(text) < 10:
                continue
            if len(text) > 20:
                bio = text
                break
        profiles.append({
            "name": name,
            "avatar": avatar,
            "appoint_date": start,
            "bio": bio,
        })
    info["profiles"] = profiles

    return info


def parse_holdings_response(text: str) -> list[dict]:
    m = re.search(r"content:\"(.+?)\",arryear:", text, re.DOTALL)
    if not m:
        return []
    content = m.group(1).replace('\\"', '"').replace("\\/", "/").replace("\\'", "'")

    quarters: list[dict] = []
    boxes = re.findall(r"<div class='box'>(.+?)(?=<div class='box'>|$)", content, re.DOTALL)
    if not boxes:
        boxes = [content]

    for box in boxes:
        tm = re.search(r"(\d{4}年\s*\d季度)", box)
        if not tm:
            continue
        quarter = tm.group(1).replace(" ", "")

        tbody_match = re.search(r"<tbody>(.+?)</tbody>", box, re.DOTALL)
        if not tbody_match:
            continue
        tbody = tbody_match.group(1)
        tr_list = re.findall(r"<tr[^>]*>(.+?)</tr>", tbody, re.DOTALL)

        stocks: list[dict] = []
        for tr in tr_list:
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
            if len(tds) < 5:
                continue
            raw = [_strip_tags(td) for td in tds]
            if not raw[0].isdigit():
                continue
            code = raw[1]
            name_m = re.search(r">([^<>]+)</a>", tds[2])
            name = name_m.group(1).strip() if name_m else raw[2]
            pct = ""
            for v in raw:
                if v.endswith("%"):
                    pct = v
                    break
            shares = raw[-2] if len(raw) >= 2 else ""
            value = raw[-1] if len(raw) >= 1 else ""
            stocks.append({
                "code": code,
                "name": name,
                "pct": pct,
                "shares": shares,
                "value": value,
            })
        if stocks:
            quarters.append({"quarter": quarter, "stocks": stocks})

    return quarters


def fetch_holdings(code: str, years: list[int]) -> list[dict]:
    all_q: list[dict] = []
    seen = set()
    for y in years:
        url = HOLDING_URL.format(code=code, year=y)
        try:
            text = _get(url)
        except Exception as e:
            print(f"  x 年份 {y} 请求失败:", e)
            continue
        qs = parse_holdings_response(text)
        for q in qs:
            if q["quarter"] in seen:
                continue
            seen.add(q["quarter"])
            all_q.append(q)
        time.sleep(random.uniform(1.0, 2.0))
    def key(q):
        m = re.match(r"(\d{4})年(\d)季度", q["quarter"])
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    all_q.sort(key=key, reverse=True)
    return all_q


def _pct_to_float(s: str) -> float:
    try:
        return float(s.replace("%", "").replace(",", "").strip())
    except Exception:
        return 0.0


def analyze(quarters: list[dict]) -> dict:
    if not quarters:
        return {}

    recent = quarters[:4]
    sets = [{s["code"] for s in q["stocks"]} for q in recent]

    if len(sets) >= 2:
        core = set.intersection(*sets)
    else:
        core = sets[0]
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
                if diff >= 0.3:
                    movements["add"].append({
                        "code": code, "name": s["name"],
                        "pct": s["pct"], "diff": round(diff, 2),
                    })
                elif diff <= -0.3:
                    movements["reduce"].append({
                        "code": code, "name": s["name"],
                        "pct": s["pct"], "diff": round(diff, 2),
                    })
                else:
                    movements["hold"].append({
                        "code": code, "name": s["name"], "pct": s["pct"],
                    })
        for code, s in prev.items():
            if code not in latest:
                movements["new_out"].append({"code": code, "name": s["name"], "pct": s["pct"]})

    def sum_top(q, n):
        return round(sum(_pct_to_float(s["pct"]) for s in q["stocks"][:n]), 2)

    concentration = []
    for q in recent:
        concentration.append({
            "quarter": q["quarter"],
            "top3": sum_top(q, 3),
            "top10": sum_top(q, 10),
        })

    core_trend: list[dict] = []
    for code in core:
        row: dict = {"code": code, "name": ""}
        series: list[dict] = []
        for q in recent:
            found = next((s for s in q["stocks"] if s["code"] == code), None)
            if found:
                row["name"] = found["name"]
                series.append({"q": q["quarter"], "pct": found["pct"]})
            else:
                series.append({"q": q["quarter"], "pct": ""})
        row["series"] = series
        core_trend.append(row)
    core_trend.sort(
        key=lambda r: _pct_to_float(r["series"][0]["pct"]) if r["series"] else 0,
        reverse=True,
    )

    latest_top5 = recent[0]["stocks"][:5] if recent else []

    def classify(stock):
        code = stock["code"]
        if code.isdigit():
            return "A股"
        return "美股/港股"

    if recent:
        buckets: dict = {"A股": 0.0, "美股/港股": 0.0}
        for s in recent[0]["stocks"]:
            buckets[classify(s)] += _pct_to_float(s["pct"])
        region = {k: round(v, 2) for k, v in buckets.items()}
    else:
        region = {}

    return {
        "core_stocks": sorted(core),
        "core_count": len(core),
        "stability_pct": stability,
        "movements": movements,
        "concentration": concentration,
        "core_trend": core_trend,
        "latest_top5": latest_top5,
        "region_mix": region,
    }


def main():
    out: dict = {"code": FUND_CODE}

    print(f"[1/3] 抓取基金主页 {FUND_CODE}")
    try:
        html = _get(FUND_URL.format(code=FUND_CODE))
        out["basic"] = parse_main(html)
    except Exception as e:
        out["basic"] = {"error": str(e)}
        print("  x 主页抓取失败:", e)
    time.sleep(random.uniform(1.0, 2.0))

    print("[2/3] 抓取基金经理页")
    try:
        html = _get(MANAGER_URL.format(code=FUND_CODE))
        out["manager"] = parse_manager(html)
    except Exception as e:
        out["manager"] = {"error": str(e)}
        print("  x 经理页抓取失败:", e)
    time.sleep(random.uniform(1.0, 2.0))

    print("[3/3] 抓取近 4 年持仓")
    from datetime import datetime
    cy = datetime.now().year
    years = [cy, cy - 1, cy - 2, cy - 3]
    out["holdings"] = fetch_holdings(FUND_CODE, years)

    out["analysis"] = analyze(out["holdings"])

    target = os.path.join(os.path.dirname(__file__), "data.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("完成 ->", target)
    print(f"  持仓季度数: {len(out['holdings'])}")
    if out['holdings']:
        print(f"  最新季: {out['holdings'][0]['quarter']}, 股票数: {len(out['holdings'][0]['stocks'])}")
    if out.get('manager', {}).get('profiles'):
        for p in out['manager']['profiles']:
            print(f"  基金经理: {p['name']}, 头像: {p['avatar']}")


if __name__ == "__main__":
    main()
