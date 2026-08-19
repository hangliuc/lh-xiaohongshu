# -*- coding: utf-8 -*-
"""
纳斯达克100指数 C类被动基金对比 · 数据抓取
数据源：天天基金网

遵循 fund-data-fetching skill 的三条铁律：
1. 候选列表通过 fundcode_search.js 动态筛选，禁止硬编码
2. 字段缺失要么重试要么标 null + _warnings，禁止伪造
3. 申购状态四态校验，关键字段交叉验证
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time

# 接入 skill 的基础工具
SKILL_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".kiro", "skills",
    "fund-data-fetching", "scripts"
))
sys.path.insert(0, SKILL_PATH)
from fetch_base import (  # noqa: E402
    get_with_retry, sleep, fetch_all_fund_codes,
    write_json, strip_tags,
)

# ──────────────────────────────────────────────
# 筛选条件
# ──────────────────────────────────────────────
KEYWORDS = ["纳斯达克100", "纳指100"]
# 仅排除真正的外币份额（人民币以外的计价单位），LOF/QDII-LOF 不属于外币
EXCLUDE_KEYWORDS = ["美元", "现汇", "现钞"]


def filter_funds(all_funds: list[list[str]]) -> list[dict]:
    """
    筛选纳斯达克100相关的 C 类被动基金（人民币份额）+ 不分 AC 的指数基金。
    输入: [[code, abbr, name, type, pinyin], ...]
    """
    out = []
    for code, abbr, name, fund_type, _ in all_funds:
        # 必须命中关键词
        if not any(k in name for k in KEYWORDS):
            continue
        # 排除场内 ETF（159xxx / 51xxxx）
        if re.match(r"^(159|51)\d+$", code):
            continue
        # 排除外币份额
        if any(t in name for t in EXCLUDE_KEYWORDS):
            continue
        # 必须是海外股票类（含 QDII / 海外股票）
        if "QDII" not in fund_type and "QDII" not in name and "海外" not in fund_type:
            continue
        # 必须是 C 类，或者不分 AC（如国泰 160213）
        # C 类标志：名称结尾形如 C / )C / 人民币C / 币C / )C(人民币)
        is_c = bool(re.search(
            r"(?:[)）]|人民币|币)C(?:\(人民币\))?$|[)）]C人民币", name))
        # A 类（要排除）
        is_a = bool(re.search(
            r"(?:[)）]|人民币|币)A(?:\(人民币\))?$|[)）]A人民币", name))
        # I/D/E/F/H/Y/Z 等其他份额（要排除）
        is_other_class = bool(re.search(
            r"(?:[)）]|人民币|币)[IDEFHYZRQ](?:\(人民币\))?$|[)）][IDEFHYZRQ]人民币", name))
        # 不分 AC：名称结尾不是任何份额字母
        is_no_class = (not is_c and not is_a and not is_other_class
                       and not re.search(r"[A-Z]$", name))

        if not (is_c or is_no_class):
            continue
        out.append({"code": code, "name": name, "type": fund_type})
    return out


# ──────────────────────────────────────────────
# 收益率（pingzhongdata 接口，比排行接口稳）
# ──────────────────────────────────────────────
def fetch_returns(code: str) -> dict:
    """从 pingzhongdata 拿近 1 月 / 3 月 / 6 月 / 1 年 / 3 年收益率"""
    out: dict = {}
    text = get_with_retry(f"http://fund.eastmoney.com/pingzhongdata/{code}.js")
    if not text:
        return out
    mapping = {
        "syl_1n": "return_1y",
        "syl_3n": "return_3y",
        "syl_6y": "return_6m",
        "syl_3y": "return_3m",
        "syl_1y": "return_1m",
    }
    for src, dst in mapping.items():
        m = re.search(rf'var\s+{src}\s*=\s*"?([\d.\-]+)"?\s*;', text)
        if m:
            out[dst] = m.group(1)
    return out


# ──────────────────────────────────────────────
# 申购状态（兼容 staticCell 多种文本格式）
# ──────────────────────────────────────────────
def parse_purchase_status_v2(html: str) -> dict:
    """
    天天基金 staticCell 现支持多种文本：
      - 开放申购
      - 暂停申购
      - 限大额 (单日累计购买上限 X 万元)
      - 暂停申购 (单日累计购买上限 X 元)   ← 新形态：实际等同限小额
    """
    info = {"purchase_status": "未知", "purchase_limit": "", "effectively_closed": False}

    # 先匹配带括号的形态（限额）
    m = re.search(
        r'staticCell">(限大额|暂停申购|限购)\s*\(<span>单日累计购买上限([\d.,]+)(万?)元</span>\)',
        html,
    )
    if m:
        prefix, amt_s, unit = m.group(1), m.group(2), m.group(3)
        amt = float(amt_s.replace(",", ""))
        if unit == "万":
            # 单位是万 → 真正的限大额（小额可正常买）
            info["purchase_status"] = "限大额"
            info["purchase_limit"] = f"{amt:g}万元/日"
        else:
            # 单位是元
            if prefix == "暂停申购":
                # "暂停申购 (单日上限 X 元)" → 基金真实状态是暂停，
                # 括号里的极小额度只是天天基金作为代销渠道留给老持仓客户的通道
                info["purchase_status"] = "暂停"
                info["purchase_limit"] = f"{amt:g}元/日(代销通道)"
                info["effectively_closed"] = True
            else:
                # "限大额 (单日上限 X 元)" 这种异常组合，按限小额处理
                info["purchase_status"] = "限小额"
                info["purchase_limit"] = f"{amt:g}元/日"
                if amt <= 1000:
                    info["effectively_closed"] = True
        return info

    # 纯文本形态
    if re.search(r'staticCell">暂停申购<', html):
        info["purchase_status"] = "暂停"
        info["purchase_limit"] = "0"
        info["effectively_closed"] = True
        return info
    if re.search(r'staticCell">开放申购<', html):
        info["purchase_status"] = "开放"
        info["purchase_limit"] = "无限制"
        return info

    return info


# ──────────────────────────────────────────────
# 单只基金详情
# ──────────────────────────────────────────────
def fetch_fund_detail(code: str) -> dict:
    info: dict = {}

    # 1. 基金主页 - 规模、申购状态
    html = get_with_retry(f"http://fund.eastmoney.com/{code}.html")
    if html:
        m = re.search(r'>规模</a>[：:]([\d,.]+)亿元', html)
        if m:
            info["scale"] = m.group(1).replace(",", "")
        info.update(parse_purchase_status_v2(html))
    sleep(0.8, 1.5)

    # 2. 档案页 - 费率、跟踪标的（覆盖主页规模）
    html = get_with_retry(f"http://fundf10.eastmoney.com/jbgk_{code}.html")
    if html:
        # 费率：仅匹配紧跟着的 <td>，避免跨字段污染
        m = re.search(r"管理费率\s*</th>\s*<td[^>]*>([\d.]+)\s*%", html)
        if m:
            info["mgmt_fee"] = float(m.group(1))
        m = re.search(r"托管费率\s*</th>\s*<td[^>]*>([\d.]+)\s*%", html)
        if m:
            info["custody_fee"] = float(m.group(1))
        m = re.search(r"销售服务费率\s*</th>\s*<td[^>]*>([\d.]+)\s*%", html)
        if m:
            info["service_fee"] = float(m.group(1))
        else:
            # ---（每年）→ 没有销售服务费
            info["service_fee"] = 0.0
        m = re.search(r"跟踪标的\s*</th>\s*<td[^>]*>(.*?)</td>", html, re.DOTALL)
        if m:
            info["benchmark"] = strip_tags(m.group(1))[:60]
        # 档案页规模（更准）
        m = re.search(r"资产规模[：:]\s*([\d.,]+)\s*亿", html, re.DOTALL)
        if m:
            info["scale"] = m.group(1).replace(",", "")
    sleep(0.8, 1.5)

    # 3. 特色数据页 - 跟踪误差
    html = get_with_retry(f"http://fundf10.eastmoney.com/tsdata_{code}.html")
    if html:
        # 结构: <td>跟踪标的名</td><td>本基金跟踪误差%</td><td>同类平均%</td>
        # 抓"跟踪误差"表头之后第一个 <td>...</td><td>X.XX%</td>
        m = re.search(
            r"跟踪误差[\s\S]*?<td[^>]*>[^<]*</td>\s*<td[^>]*>([\d.]+)\s*%",
            html,
        )
        if m:
            info["tracking_error"] = float(m.group(1))
    sleep(0.5, 1.0)

    # 综合费率
    fees = [info.get("mgmt_fee", 0), info.get("custody_fee", 0),
            info.get("service_fee", 0)]
    if any(f > 0 for f in fees):
        info["total_fee"] = round(sum(fees), 4)

    return info


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    print("=" * 60)
    print("纳斯达克100 C类被动基金 · 数据抓取")
    print("=" * 60)

    # Step 1：全市场清单
    print("\n[1/4] 拉取全市场基金清单 ...")
    all_funds = fetch_all_fund_codes()
    print(f"  → 全市场基金总数: {len(all_funds)}")

    # Step 2：动态筛选
    print("\n[2/4] 按主题 / 份额筛选 ...")
    targets = filter_funds(all_funds)
    print(f"  → 符合条件: {len(targets)} 只")
    for f in targets:
        print(f"    {f['code']} | {f['name']} | {f['type']}")
    if not targets:
        print("  ✗ 未找到符合条件的基金")
        return

    # Step 3：批量收益率（从 pingzhongdata 一只一只拿，更稳）
    print(f"\n[3/4] 抓取详情（{len(targets)} 只 · 含收益率/规模/费率/跟踪误差）...")
    warnings: list = []
    results = []
    for i, fund in enumerate(targets, 1):
        code, name = fund["code"], fund["name"]
        print(f"  [{i}/{len(targets)}] {code} {name}")
        entry = {"code": code, "name": name}
        # 收益率
        ret = fetch_returns(code)
        if not ret.get("return_1y"):
            warnings.append(f"{code}_no_return_1y")
        entry.update(ret)
        sleep(0.5, 1.0)
        # 主页 + 档案 + 跟踪误差
        entry.update(fetch_fund_detail(code))

        # 关键字段缺失告警
        for key in ["scale", "return_1y", "tracking_error", "total_fee",
                    "purchase_status"]:
            v = entry.get(key)
            if v is None or v == "" or v == "未知":
                warnings.append(f"{code}_missing_{key}")

        results.append(entry)
        sleep(0.5, 1.0)

    # 按近 1 年收益率排序
    def sk(f):
        try:
            return float(str(f.get("return_1y", "0")).replace(",", ""))
        except Exception:
            return 0.0
    results.sort(key=sk, reverse=True)

    output = {
        "title": "纳斯达克100指数C类被动基金对比",
        "update_date": time.strftime("%Y-%m-%d"),
        "fetch_date": time.strftime("%Y-%m-%d"),
        "count": len(results),
        "fund_count": len(results),
        "_warnings": warnings,
        "funds": results,
    }
    target = os.path.join(os.path.dirname(__file__), "data.json")
    write_json(target, output)

    # 控制台汇总（强制人工抽检）
    print("\n" + "=" * 60)
    print(f"汇总（{len(results)} 只 · 按近1年收益率倒序）")
    print("=" * 60)
    for r in results:
        scale = r.get("scale", "?")
        ret = r.get("return_1y", "?")
        fee = r.get("total_fee", "?")
        te = r.get("tracking_error", "?")
        status = r.get("purchase_status", "?")
        flag = " ⚠EFF_CLOSED" if r.get("effectively_closed") else ""
        print(f"  {r['code']} | {r['name'][:26]:<26} | "
              f"规模 {scale}亿 | 1Y {ret}% | 费 {fee}% | TE {te}% | {status}{flag}")
    if warnings:
        print(f"\n⚠ Warnings ({len(warnings)}): {warnings}")
    else:
        print("\n✓ 无字段告警")


if __name__ == "__main__":
    main()
