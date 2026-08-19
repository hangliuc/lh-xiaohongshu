# -*- coding: utf-8 -*-
# 数据来源：用户在 2026-07-21 对话中明确指定 20 只 QDII 主动基金代码，非自动筛选结果
# 数据基准：2026年第2季度报告（截止 2026-06-30，披露截止 2026-07-21）
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta

import pdfplumber
import requests

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

CSRC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "http://eid.csrc.gov.cn/fund/disclose/advanced_search.html",
}

FUND_LIST = [
    {"code": "017437", "display": "华宝纳斯达克精选", "main_code": "017436", "short_name": "华宝纳斯达克精选"},
    {"code": "014002", "display": "浦银安盛全球智能科技", "main_code": "014001", "short_name": "浦银安盛全球智能科技"},
    {"code": "021277", "display": "广发全球精选", "main_code": "021276", "short_name": "广发全球精选"},
    {"code": "017731", "display": "嘉实全球产业升级", "main_code": "017730", "short_name": "嘉实全球产业升级"},
    {"code": "000043", "display": "嘉实美国成长", "main_code": "000043", "short_name": "嘉实美国成长"},
    {"code": "161128", "display": "易方达标普信息科技", "main_code": "161128", "short_name": "易方达标普信息科技"},
    {"code": "012922", "display": "易方达全球成长精选", "main_code": "012920", "short_name": "易方达全球成长精选"},
    {"code": "021842", "display": "国富全球科技", "main_code": "021841", "short_name": "国富全球科技互联"},
    {"code": "539002", "display": "建信新兴市场混合", "main_code": "539002", "short_name": "建信新兴市场"},
    {"code": "015202", "display": "汇添富全球移动互联", "main_code": "015201", "short_name": "汇添富全球移动互联"},
    {"code": "024239", "display": "华夏全球科技先锋", "main_code": "024238", "short_name": "华夏全球科技先锋"},
    {"code": "016702", "display": "银华海外数字经济", "main_code": "016701", "short_name": "银华海外数字经济"},
    {"code": "018036", "display": "长城全球新能源车", "main_code": "018035", "short_name": "长城全球新能源车"},
    {"code": "022184", "display": "富国全球科技互联网", "main_code": "100055", "short_name": "富国全球科技互联网"},
    {"code": "017204", "display": "华宝海外科技", "main_code": "017203", "short_name": "华宝海外科技"},
    {"code": "008254", "display": "华宝致远混合", "main_code": "008253", "short_name": "华宝致远"},
    {"code": "017093", "display": "景顺长城纳斯达克科技", "main_code": "017092", "short_name": "景顺长城纳斯达克科技"},
    {"code": "016665", "display": "天弘全球高端制造", "main_code": "016664", "short_name": "天弘全球高端制造"},
    {"code": "002891", "display": "华夏移动互联", "main_code": "002891", "short_name": "华夏移动互联"},
    {"code": "021662", "display": "国富亚洲机会", "main_code": "457001", "short_name": "国富亚洲机会"},
]

MAIN_URL = "http://fund.eastmoney.com/{code}.html"
HOLDINGS_URL = (
    "http://fundf10.eastmoney.com/FundArchivesDatas.aspx"
    "?type=jjcc&code={code}&topline=10&year={year}&month=&rt=0.1"
)
NAV_URL = (
    "https://api.fund.eastmoney.com/f10/lsjz"
    "?callback=jQuery&fundCode={code}&pageIndex={page}&pageSize=20"
    "&startDate={start}&endDate={end}"
)
CSRC_SEARCH_URL = "http://eid.csrc.gov.cn/fund/disclose/advanced_search_report.do"
CSRC_PDF_URL = "http://eid.csrc.gov.cn/fund/disclose/instance_show_pdf_id.do?instanceid={instanceid}"


def _get(url: str, timeout: int = 20, headers: dict | None = None) -> str | None:
    try:
        h = headers or HEADERS
        resp = requests.get(url, headers=h, timeout=timeout)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            print(f"  ! HTTP {resp.status_code} - {url[:80]}")
            return None
        return resp.text
    except Exception as e:
        print(f"  ! 请求失败: {url[:80]} - {e}")
        return None


def _sleep(lo: float = 0.5, hi: float = 2.0) -> None:
    time.sleep(random.uniform(lo, hi))


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def parse_purchase_status(html: str) -> dict:
    info = {"purchase_status": "未知", "purchase_limit": "", "effectively_closed": False}

    # 优先识别"暂停申购"——天天基金的 staticCell 即使写着「暂停申购 (单日累计购买上限 X 元)」，
    # 也表示当前完全不能买（限额是"假如恢复申购"的兜底值）。直接判定为暂停。
    if re.search(r'staticCell[^>]*>\s*暂停申购', html):
        info["purchase_status"] = "暂停"
        info["purchase_limit"] = "0"
        info["effectively_closed"] = True
        return info

    m = re.search(r'单日累计购买上限([\d.,]+)(万?)元', html)
    if m:
        amt = float(m.group(1).replace(",", ""))
        unit = m.group(2)
        if unit == "万":
            info["purchase_limit"] = f"{amt:g}万"
            info["purchase_status"] = "限大额"
        else:
            info["purchase_limit"] = f"{amt:g}元"
            info["purchase_status"] = "限小额"
            if amt <= 1000:
                info["effectively_closed"] = True
        return info

    if re.search(r'staticCell[^>]*>\s*开放申购', html):
        info["purchase_status"] = "开放"
        info["purchase_limit"] = "无限制"
        return info

    return info


def fetch_main_page(code: str) -> dict:
    info = {}
    html = _get(MAIN_URL.format(code=code))
    if not html:
        return info

    m = re.search(r"<title>(.*?)\((\d{6})\)", html)
    if m:
        info["name"] = m.group(1).strip()

    for label in ["近1年", "近一年"]:
        m = re.search(
            re.escape(label) + r"[：:]\s*</span>\s*<span[^>]*>([-\d.]+)%?</span>",
            html,
        )
        if m:
            info["return_1y"] = m.group(1)
            break

    info.update(parse_purchase_status(html))
    return info


def fetch_holdings(code: str, year: int = 2026) -> list[dict]:
    text = _get(HOLDINGS_URL.format(code=code, year=year))
    if not text:
        return []

    m = re.search(r"content:\"(.+?)\",arryear:", text, re.DOTALL)
    if not m:
        return []
    content = m.group(1).replace('\\"', '"').replace("\\/", "/").replace("\\'", "'")

    stocks = []
    tbody = re.search(r"<tbody>(.+?)</tbody>", content, re.DOTALL)
    if not tbody:
        return stocks
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
        stocks.append({"code": raw[1], "name": name, "pct": pct})
    return stocks


def infer_focus_direction(stocks: list[dict]) -> str:
    if not stocks:
        return ""
    names = [s["name"] for s in stocks[:10]]

    tech_keywords = ["英伟达", "苹果", "微软", "谷歌", "亚马逊", "Meta", "奈飞",
                     "博通", "迈威尔", "AMD", "英特尔", "高通", "台积电",
                     "特斯拉", "甲骨文", "赛富时", "Adobe", "思科"]
    ev_keywords = ["特斯拉", "比亚迪", "宁德时代", "理想汽车", "蔚来", "小鹏",
                   "Rivian", "Lucid", "锂", "电池", "新能源车", "小马智行"]
    internet_keywords = ["腾讯", "阿里巴巴", "美团", "拼多多", "京东", "百度",
                         "网易", "快手", "字节", "SEA"]
    semiconductor_keywords = ["英伟达", "博通", "AMD", "台积电", "迈威尔",
                              "ASML", "高通", "英特尔", "SK海力士", "美光",
                              "新易盛", "中际旭创", "源杰科技", "康宁"]

    tech_count = sum(1 for n in names if any(k in n for k in tech_keywords))
    ev_count = sum(1 for n in names if any(k in n for k in ev_keywords))
    internet_count = sum(1 for n in names if any(k in n for k in internet_keywords))
    semi_count = sum(1 for n in names if any(k in n for k in semiconductor_keywords))

    scores = {
        "科技巨头": tech_count,
        "半导体": semi_count,
        "新能源车": ev_count,
        "互联网": internet_count,
    }
    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        return best
    return "科技"


def fetch_drawdown(code: str) -> str | None:
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    all_navs = []
    page = 1
    consecutive_empty = 0
    while True:
        url = NAV_URL.format(code=code, page=page, start=start, end=end)
        text = _get(url)
        if not text:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
            page += 1
            continue
        m = re.search(r"jQuery\((.*)\)", text, re.DOTALL)
        if not m:
            break
        data = json.loads(m.group(1))
        lsjz = (data.get("Data") or {}).get("LSJZList", [])
        if not lsjz:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
            page += 1
            continue
        consecutive_empty = 0
        for item in lsjz:
            try:
                all_navs.append((item["FSRQ"], float(item["DWJZ"])))
            except (ValueError, KeyError):
                continue
        total = data.get("TotalCount", 0)
        if len(all_navs) >= total or len(lsjz) < 20:
            break
        page += 1
        time.sleep(random.uniform(0.3, 0.6))

    if len(all_navs) < 20:
        print(f"  ! 回撤: 仅获取到 {len(all_navs)} 条NAV记录")
        return None

    all_navs.sort(key=lambda x: x[0])

    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    navs_1y = [(d, n) for d, n in all_navs if d >= one_year_ago]
    if len(navs_1y) < 20:
        navs_1y = all_navs

    peak = navs_1y[0][1]
    max_dd = 0.0
    for _, nav in navs_1y:
        if nav > peak:
            peak = nav
        dd = (peak - nav) / peak
        if dd > max_dd:
            max_dd = dd

    return f"{max_dd * 100:.2f}"


def _csrc_search(fund_code: str = "", fund_short_name: str = "") -> str | None:
    aoData = [
        {"name": "sEcho", "value": 1},
        {"name": "iColumns", "value": 6},
        {"name": "sColumns", "value": ""},
        {"name": "iDisplayStart", "value": 0},
        {"name": "iDisplayLength", "value": 20},
        {"name": "mDataProp_0", "value": "fund"},
        {"name": "mDataProp_1", "value": "fund"},
        {"name": "mDataProp_2", "value": "reportName"},
        {"name": "mDataProp_3", "value": "reportName"},
        {"name": "mDataProp_4", "value": "reportDesp"},
        {"name": "mDataProp_5", "value": "reportSendDate"},
        {"name": "iSortingCols", "value": 0},
        {"name": "fundType", "value": ""},
        {"name": "reportType", "value": "FB030"},
        {"name": "reportYear", "value": "2026"},
        {"name": "fundCompanyShortName", "value": ""},
        {"name": "fundCode", "value": fund_code},
        {"name": "fundShortName", "value": fund_short_name},
        {"name": "startUploadDate", "value": ""},
        {"name": "endUploadDate", "value": ""},
    ]
    try:
        resp = requests.get(
            CSRC_SEARCH_URL,
            params={"aoData": json.dumps(aoData)},
            headers=CSRC_HEADERS,
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        records = data.get("aaData", [])
        if not records:
            return None
        for item in records:
            report_name = item.get("reportName", "")
            if "第2季度" in report_name or "第二季度" in report_name:
                return str(item.get("uploadInfoId", ""))
        # 若尚未披露 Q2，回退 Q1
        for item in records:
            report_name = item.get("reportName", "")
            if "第1季度" in report_name or "第一季度" in report_name:
                return str(item.get("uploadInfoId", ""))
        if records:
            return str(records[0].get("uploadInfoId", ""))
    except Exception as e:
        print(f"    ! CSRC搜索失败: {e}")
    return None


def find_csrc_instance_id(main_code: str, short_name: str = "") -> str | None:
    instance_id = _csrc_search(fund_code=main_code)
    if instance_id:
        return instance_id
    if short_name:
        instance_id = _csrc_search(fund_short_name=short_name)
        if instance_id:
            return instance_id
    return None


def parse_market_distribution_from_pdf(pdf_content: bytes) -> dict:
    """解析季报PDF的"报告期末在各个国家（地区）证券市场的股票及存托凭证投资分布"表格。

    需处理表格跨页情况：表头出现在一页，数据行出现在下一页。因此把 in_section
    状态在页与页之间保持，遇到合计/注/说明性文字才结束。
    """
    result = {}
    country_re = re.compile(
        r'(美国|中国内地|中国大陆|中国香港|中国台湾|中国|日本|韩国|英国|德国|法国|印度|新加坡|澳大利亚|加拿大|瑞士|荷兰|巴西|以色列|开曼群岛|百慕大|台湾|香港|意大利|西班牙|越南|印度尼西亚|马来西亚|泰国|菲律宾)\s+[\d,，.]+\s+([\d.]+)'
    )
    try:
        import io
        pdf = pdfplumber.open(io.BytesIO(pdf_content))
        in_section = False
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = text.split("\n")
            for line in lines:
                stripped = line.strip()
                # 进入表格：任何行同时含"国家"和(公允|比例|资产净值)
                if ("国家" in stripped) and (
                    "公允" in stripped or "比例" in stripped or "资产净值" in stripped
                ) and "合计" not in stripped:
                    in_section = True
                    continue
                if not in_section:
                    continue
                if stripped.startswith("合计") or stripped.startswith("注") or stripped.startswith("5."):
                    in_section = False
                    continue
                m = country_re.match(stripped)
                if m:
                    country = m.group(1)
                    if country in ("中国", "中国大陆"):
                        country = "中国内地"
                    if country == "台湾":
                        country = "中国台湾"
                    if country == "香港":
                        country = "中国香港"
                    # 只保留首次出现（首个表通常就是最完整的）
                    if country not in result:
                        result[country] = float(m.group(2))
        pdf.close()
    except Exception as e:
        print(f"    ! PDF解析失败: {e}")
    return result


def fetch_market_distribution(main_code: str, short_name: str = "") -> dict:
    print(f"    CSRC搜索 {main_code}")
    instance_id = find_csrc_instance_id(main_code, short_name)
    if not instance_id:
        print(f"    ! 未找到季报instance ID")
        return {}

    print(f"    获取季报PDF instanceid={instance_id}")
    pdf_url = CSRC_PDF_URL.format(instanceid=instance_id)
    try:
        resp = requests.get(pdf_url, headers=CSRC_HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"    ! 季报PDF获取失败 HTTP {resp.status_code}")
            return {}
        dist = parse_market_distribution_from_pdf(resp.content)
        if dist:
            print(f"    市场分布: {dist}")
        else:
            print(f"    ! 未找到市场分布数据")
        return dist
    except Exception as e:
        print(f"    ! 季报PDF获取失败: {e}")
        return {}


def fetch_fund(fund_info: dict) -> dict:
    code = fund_info["code"]
    display = fund_info["display"]
    main_code = fund_info["main_code"]
    result = {
        "code": code,
        "display_name": display,
        "name": "",
        "return_1y": None,
        "drawdown_1y": None,
        "purchase_limit": "",
        "purchase_status": "未知",
        "effectively_closed": False,
        "market_distribution": {},
        "focus_direction": "",
        "top10_holdings": [],
    }

    print(f"  [1/4] 主页 {code}")
    main_info = fetch_main_page(code)
    result["name"] = main_info.get("name", "")
    result["return_1y"] = main_info.get("return_1y")
    result["purchase_status"] = main_info.get("purchase_status", "未知")
    result["purchase_limit"] = main_info.get("purchase_limit", "")
    result["effectively_closed"] = main_info.get("effectively_closed", False)
    _sleep(0.8, 1.5)

    print(f"  [2/4] 持仓 {code}")
    holdings = []
    for y in [2026, 2025, 2024, 2023]:
        holdings = fetch_holdings(code, year=y)
        if holdings:
            break
    result["top10_holdings"] = holdings[:10]
    result["focus_direction"] = infer_focus_direction(holdings)
    _sleep(0.8, 1.5)

    print(f"  [3/4] 回撤 {code}")
    dd = fetch_drawdown(code)
    if dd:
        result["drawdown_1y"] = dd
    _sleep(0.5, 1.0)

    print(f"  [4/4] 市场分布 {code} (主代码: {main_code})")
    dist = fetch_market_distribution(main_code, fund_info.get("short_name", ""))
    result["market_distribution"] = dist
    _sleep(0.5, 1.0)

    return result


def main():
    print("=" * 60)
    print("纳斯达克100主动基金数据抓取 v2")
    print("=" * 60)

    results = []
    warnings = []

    for i, fund in enumerate(FUND_LIST, 1):
        print(f"\n[{i}/{len(FUND_LIST)}] {fund['code']} {fund['display']}")
        try:
            entry = fetch_fund(fund)
        except Exception as e:
            print(f"  ! 抓取失败: {e}")
            import traceback
            traceback.print_exc()
            entry = {
                "code": fund["code"],
                "display_name": fund["display"],
                "name": "",
                "return_1y": None,
                "drawdown_1y": None,
                "purchase_limit": "",
                "purchase_status": "未知",
                "effectively_closed": False,
                "market_distribution": {},
                "focus_direction": "",
                "top10_holdings": [],
            }
            warnings.append(f"{fund['code']}_fetch_failed")

        missing = []
        if not entry["name"]:
            missing.append("name")
        if entry["return_1y"] is None:
            missing.append("return_1y")
        if entry["drawdown_1y"] is None:
            missing.append("drawdown_1y")
        if not entry["market_distribution"]:
            missing.append("market_distribution")
        if missing:
            warnings.append(f"{fund['code']}_missing_{','.join(missing)}")
            print(f"  ! 缺失字段: {missing}")

        results.append(entry)

    output = {
        "update_date": time.strftime("%Y-%m-%d"),
        "count": len(results),
        "_warnings": warnings,
        "funds": results,
    }

    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n完成 → {target}（{len(results)} 只）")

    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    for r in results:
        ret = r.get("return_1y", "?")
        dd = r.get("drawdown_1y", "?")
        limit = r.get("purchase_limit", "?")
        status = r.get("purchase_status", "?")
        focus = r.get("focus_direction", "?")
        mkt = r.get("market_distribution", {})
        mkt_str = " / ".join(f"{k}:{v}%" for k, v in mkt.items())
        flag = " ⚠EFF_CLOSED" if r.get("effectively_closed") else ""
        print(
            f"  {r['code']} | {r['display_name']:<16} | "
            f"1Y收益:{ret}% | 回撤:{dd}% | 限额:{limit} | "
            f"{status}{flag} | {focus} | {mkt_str}"
        )
    if warnings:
        print(f"\n⚠ Warnings: {warnings}")


if __name__ == "__main__":
    main()
