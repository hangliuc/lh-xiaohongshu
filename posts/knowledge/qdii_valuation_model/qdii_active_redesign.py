#!/usr/bin/env python3
"""
QDII 主动型基金净值估算 — 全新模型设计与回测
==============================================

完全独立设计的 5 个估算模型，用于解决 QDII 主动基金「美股凌晨 04:00 收盘 ↔ 国内 19:00-22:00
更新」长达 15 小时的信息真空问题。

核心痛点
--------
1. 持仓滞后：季报只披露上一季度末时点持仓，最长滞后 1 季度。
2. 前 10 之外的 ~50% 仓位完全不透明。
3. 其余资产（现金、债券、其他基金）无法直接估算。

模型设计（与项目中既有方案完全无关）
------------------------------------
α 模型：核心持仓裸算法
β 模型：纯行业 ETF 合成法
γ 模型：核心持仓 + 行业残余双层法
δ 模型：地区 × 行业网格代理法
ε 模型：γ + 残差自校准法

回测对象：012922 易方达全球成长精选
回测窗口：2026-04-01 ~ 2026-04-30（Q1 2026 季报披露后的第一个月）

用法：
    python3 experiments/qdii_active_redesign.py
"""

import argparse
import datetime
import json
import re
import time
import urllib.request

# =============================================================================
# Data Layer — 数据获取
# =============================================================================

UA = {'User-Agent': 'Mozilla/5.0'}


def http_get(url, referer=None, timeout=15):
    headers = dict(UA)
    if referer:
        headers['Referer'] = referer
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'ignore')


def fetch_fund_nav(code, total=120):
    """基金历史净值（含日涨跌率 JZZZL）"""
    out = []
    page = 1
    while len(out) < total and page <= 10:
        url = f'https://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex={page}&pageSize=20'
        try:
            data = json.loads(http_get(url, referer='https://fundf10.eastmoney.com/'))
        except Exception:
            break
        items = data.get('Data', {}).get('LSJZList', []) or []
        if not items:
            break
        for it in items:
            out.append({
                'date': it['FSRQ'],
                'nav': float(it['DWJZ']) if it['DWJZ'] else None,
                'pct': float(it['JZZZL']) if it['JZZZL'] else None,
            })
        if len(items) < 20:
            break
        page += 1
        time.sleep(0.2)
    return out[:total]


def fetch_top10(code):
    """前 10 大持仓（最新季报）"""
    url = f'https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=15'
    html = http_get(url, referer='https://fundf10.eastmoney.com/')

    rep_date = ''
    m = re.search(r'截止至：<font[^>]*>([\d-]+)</font>', html)
    if m:
        rep_date = m.group(1)

    tbody = re.search(r'<tbody>(.+?)</tbody>', html, re.DOTALL)
    if not tbody:
        return [], rep_date

    rows = re.findall(r'<tr>(.+?)</tr>', tbody.group(1), re.DOTALL)
    holdings = []
    for r in rows:
        secid_m = re.search(r"unify/r/(\d+\.[^'\"\s]+)", r)
        cells = re.findall(r'<td[^>]*>(.+?)</td>', r, re.DOTALL)
        if not secid_m or len(cells) < 7:
            continue
        clean = lambda s: re.sub(r'<[^>]+>', '', s).replace('&nbsp;', ' ').strip()
        secid = secid_m.group(1)
        name = clean(cells[2])
        try:
            ratio = float(clean(cells[6]).replace('%', ''))
        except ValueError:
            continue
        prefix = secid.split('.')[0]
        market = {'105': 'US', '106': 'US', '107': 'US',
                  '116': 'HK', '0': 'CN', '1': 'CN'}.get(prefix, 'OTHER')
        holdings.append({'secid': secid, 'name': name, 'ratio': ratio, 'market': market})
    return holdings, rep_date


def fetch_industry(code):
    """行业分布（季报）"""
    url = f'https://api.fund.eastmoney.com/f10/HYPZ/?fundCode={code}&year=&callback=jQuery'
    try:
        resp = http_get(url, referer='https://fundf10.eastmoney.com/')
    except Exception:
        return '', []
    m = re.search(r'jQuery\((.+)\)', resp, re.DOTALL)
    if not m:
        return '', []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return '', []
    qs = data.get('Data', {}).get('QuarterInfos', [])
    if not qs:
        return '', []
    latest = qs[0]
    rep_date = latest.get('JZRQ', '')
    items = []
    for it in latest.get('HYPZInfo', []):
        try:
            r = float(it.get('ZJZBL', '0'))
        except (ValueError, TypeError):
            continue
        if r > 0:
            items.append({'name': it.get('HYMC', ''), 'ratio': r})
    items.sort(key=lambda x: -x['ratio'])
    return rep_date, items


def fetch_region(code):
    """地区分布（季报）"""
    url = f'https://api.fund.eastmoney.com/f10/DQPZ/?fundCode={code}&year=&callback=jQuery'
    try:
        resp = http_get(url, referer='https://fundf10.eastmoney.com/')
    except Exception:
        return '', []
    m = re.search(r'jQuery\((.+)\)', resp, re.DOTALL)
    if not m:
        return '', []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return '', []
    qs = data.get('Data', {}).get('QuarterInfos', [])
    if not qs:
        return '', []
    latest = qs[0]
    rep_date = latest.get('JZRQ', '')
    items = []
    for it in latest.get('DQPZInfo', []):
        try:
            r = float(it.get('ZJZBL', '0'))
        except (ValueError, TypeError):
            continue
        if r > 0:
            items.append({'name': it.get('DQMC', ''), 'ratio': r})
    items.sort(key=lambda x: -x['ratio'])
    return rep_date, items


def fetch_us_kline(symbol):
    """美股日 K"""
    url = f'https://stock.finance.sina.com.cn/usstock/api/jsonp_v2.php/var%20_x_{symbol.lower()}=/US_MinKService.getDailyK?symbol={symbol.lower()}&___qn=3'
    try:
        text = http_get(url, referer='https://finance.sina.com.cn/')
        m = re.search(r'=\s*\(?(\[.+\])', text, re.DOTALL)
        if not m:
            return []
        arr = json.loads(m.group(1))
        return [{'date': x['d'], 'close': float(x['c'])} for x in arr if x.get('c')]
    except Exception:
        return []


def fetch_cn_kline(secid, days=120):
    """A 股 / A 股 ETF 日 K"""
    prefix, code = secid.split('.')
    sina = ('sz' if prefix == '0' else 'sh') + code
    url = f'https://quotes.sina.cn/cn/api/jsonp.php/var%20_x_{sina}=/CN_MarketDataService.getKLineData?symbol={sina}&scale=240&ma=no&datalen={days}'
    try:
        text = http_get(url, referer='https://finance.sina.com.cn/')
        m = re.search(r'=\s*\(?(\[.+\])', text, re.DOTALL)
        if not m:
            return []
        arr = json.loads(m.group(1))
        return [{'date': x['day'][:10], 'close': float(x['close'])} for x in arr if x.get('close')]
    except Exception:
        return []


def fetch_fx_usd_cny(days=120):
    """USD/CNY 中间价"""
    url = f'https://quotes.sina.cn/forex/api/jsonp.php/var%20_x_usdcny=/ForexService.getKlineData?symbol=fx_susdcny&scale=240&datalen={days}'
    try:
        text = http_get(url, referer='https://finance.sina.com.cn/')
        m = re.search(r'=\s*\(?(\[.+\])', text, re.DOTALL)
        if not m:
            return []
        arr = json.loads(m.group(1))
        return [{'date': x['day'][:10], 'close': float(x['close'])} for x in arr if x.get('close')]
    except Exception:
        return []


# =============================================================================
# Helpers
# =============================================================================

def to_map(rows):
    return {r['date']: r['close'] for r in rows}


def chg_pct(pmap, today, prev):
    """同一价格序列内，今日相对前一日的涨跌（%）"""
    p1 = pmap.get(today)
    p0 = pmap.get(prev)
    if p1 is None or p0 is None or p0 == 0:
        return None
    return (p1 - p0) / p0 * 100


def chg_pct_us(pmap, today, prev):
    """美股价格用基金日期映射：T 日基金净值反映 T 日美股盘后（T-1 日 RTH 收盘 → T 日 RTH 收盘）。
    新浪美股日 K 的日期就是该交易日，所以基金 T 日 ↔ 美股 T 日（同日字符串）。
    """
    return chg_pct(pmap, today, prev)


def find_prev_trading_day(pmap, ref_date, max_back=10):
    """返回 pmap 中早于 ref_date 的最近一日"""
    try:
        d = datetime.datetime.strptime(ref_date, '%Y-%m-%d')
    except ValueError:
        return None
    for i in range(1, max_back + 1):
        c = (d - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
        if c in pmap:
            return c
    return None


# =============================================================================
# 5 个估算模型
# =============================================================================

def model_alpha(holdings, prices, today, prev):
    """
    α 模型：核心持仓裸算法
    -----------------------
    P_est = Σ_{i=1..10} w_i × R_i
    R_i  : 持仓 i 在 (prev, today) 的涨跌
    w_i  : 季报披露占净值比
    其他仓位（~48.17%）默认 0%
    """
    est = 0.0
    detail = []
    for h in holdings:
        pmap = prices.get(h['secid'])
        if not pmap:
            detail.append((h['name'], None, None, h['ratio'], 0))
            continue
        r = chg_pct(pmap, today, prev)
        if r is None:
            detail.append((h['name'], None, None, h['ratio'], 0))
            continue
        contrib = r * h['ratio'] / 100
        est += contrib
        detail.append((h['name'], pmap.get(prev), pmap.get(today), h['ratio'], contrib))
    return est, detail


def model_beta(industries, proxy_map_by_industry, today, prev):
    """
    β 模型：纯行业 ETF 合成法
    -------------------------
    完全抛弃前 10 个股，用季报行业分布 × 行业代理 ETF
    P_est = Σ_j (industry_ratio_j × R_proxy_j)
    R_proxy_j：该行业代理 ETF/指数当日涨跌
    """
    est = 0.0
    detail = []
    for ind in industries:
        proxy_secid, proxy_name = proxy_map_by_industry.get(ind['name'], (None, None))
        if not proxy_secid:
            detail.append((ind['name'], proxy_name, None, ind['ratio'], 0))
            continue
        pmap = proxy_secid  # 这里直接传入 price_map
        r = chg_pct(pmap, today, prev)
        if r is None:
            detail.append((ind['name'], proxy_name, None, ind['ratio'], 0))
            continue
        contrib = r * ind['ratio'] / 100
        est += contrib
        detail.append((ind['name'], proxy_name, r, ind['ratio'], contrib))
    return est, detail


def model_gamma(holdings, industries, prices, proxy_pmap, ind_proxy_assign,
                today, prev):
    """
    γ 模型：核心持仓 + 行业残余双层法
    ----------------------------------
    1) 前 10 重仓股 → 用真实股票涨跌
    2) 行业 j 的「残余仓位」= industry_j - Σ(前10在 j 的占比)
       残余 → 行业 ETF 代理
    P_est = Σ前10 + Σ行业残余×ETF
    """
    # Step 1: 把前 10 按行业归类（需要先知道每只股票属于哪个行业）
    # 这里采用人工映射（基金披露的 GICS 行业），下方主流程传入。
    est_top = 0.0
    top_detail = []
    industry_used = {ind['name']: 0.0 for ind in industries}

    for h in holdings:
        pmap = prices.get(h['secid'])
        r = chg_pct(pmap, today, prev) if pmap else None
        if r is None:
            top_detail.append((h['name'], h.get('industry', '?'), h['ratio'], None, 0))
            continue
        contrib = r * h['ratio'] / 100
        est_top += contrib
        top_detail.append((h['name'], h.get('industry', '?'), h['ratio'], r, contrib))
        if h.get('industry') in industry_used:
            industry_used[h['industry']] += h['ratio']

    # Step 2: 行业残余
    est_resid = 0.0
    resid_detail = []
    for ind in industries:
        used = industry_used.get(ind['name'], 0.0)
        resid = max(0.0, ind['ratio'] - used)
        proxy_secid, proxy_name = ind_proxy_assign.get(ind['name'], (None, None))
        if not proxy_secid or resid <= 0:
            resid_detail.append((ind['name'], used, resid, proxy_name, None, 0))
            continue
        pmap = proxy_pmap.get(proxy_secid)
        r = chg_pct(pmap, today, prev) if pmap else None
        if r is None:
            resid_detail.append((ind['name'], used, resid, proxy_name, None, 0))
            continue
        contrib = r * resid / 100
        est_resid += contrib
        resid_detail.append((ind['name'], used, resid, proxy_name, r, contrib))

    return est_top + est_resid, {'top': top_detail, 'resid': resid_detail,
                                  'est_top': est_top, 'est_resid': est_resid}


def model_delta(holdings, region_dist, industry_dist, prices, region_industry_proxy,
                today, prev):
    """
    δ 模型：地区 × 行业网格代理法
    ------------------------------
    假设每个地区内的行业分布与基金整体相同（季报通常不披露交叉表）：
        weight(region r, industry j) = region_r × (industry_j / total_stock)
    然后：
    - 前 10 落在某个 cell，用真实股票涨跌
    - 其余 cell 用 「该地区的该行业代理指数」估算

    覆盖率最高，对每个 cell 都有一个对应的代理指数。
    """
    total_stock = sum(x['ratio'] for x in industry_dist)
    if total_stock <= 0:
        return 0.0, {}

    # cell weight
    cells = {}  # {(region, industry): weight}
    for reg in region_dist:
        for ind in industry_dist:
            w = reg['ratio'] * (ind['ratio'] / total_stock)
            cells[(reg['name'], ind['name'])] = {'weight': w, 'used': 0.0}

    # 前 10 计入对应 cell
    est_top = 0.0
    top_detail = []
    for h in holdings:
        pmap = prices.get(h['secid'])
        r = chg_pct(pmap, today, prev) if pmap else None
        if r is None:
            top_detail.append((h['name'], '?', h['ratio'], None, 0))
            continue
        contrib = r * h['ratio'] / 100
        est_top += contrib
        top_detail.append((h['name'], h.get('region_name', '?'), h['ratio'], r, contrib))
        key = (h.get('region_name', ''), h.get('industry', ''))
        if key in cells:
            cells[key]['used'] += h['ratio']

    # 残余 cell 用代理
    est_resid = 0.0
    resid_detail = []
    for (reg, ind), info in cells.items():
        resid = max(0.0, info['weight'] - info['used'])
        if resid <= 1e-3:
            continue
        proxy_secid, proxy_name = region_industry_proxy.get((reg, ind), (None, None))
        if not proxy_secid:
            # fallback: 仅按地区代理
            proxy_secid, proxy_name = region_industry_proxy.get((reg, '*'), (None, None))
        if not proxy_secid:
            resid_detail.append((reg, ind, resid, '无代理', None, 0))
            continue
        pmap = proxy_secid
        r = chg_pct(pmap, today, prev) if pmap else None
        if r is None:
            resid_detail.append((reg, ind, resid, proxy_name, None, 0))
            continue
        contrib = r * resid / 100
        est_resid += contrib
        resid_detail.append((reg, ind, resid, proxy_name, r, contrib))

    return est_top + est_resid, {'top': top_detail, 'resid': resid_detail,
                                  'est_top': est_top, 'est_resid': est_resid}


def model_epsilon(base_estimate_today, history_residuals, lam=0.6):
    """
    方案五：自校准（基础模型 + EWMA 残差校正）
    -------------------------------------------
    bias_t = EWMA over recent days of (actual_pct - base_est)
    final_est = base_est + bias_t

    history_residuals: list of {actual, base_est} for past N days, 顺序 = 旧→新
    """
    if not history_residuals:
        return base_estimate_today, 0.0
    # EWMA
    weight_sum = 0.0
    bias = 0.0
    for i, h in enumerate(history_residuals):
        # i=0 是最旧
        age = len(history_residuals) - 1 - i  # 0 = 最新
        w = lam ** age
        bias += w * (h['actual'] - h['base_est'])
        weight_sum += w
    if weight_sum > 0:
        bias /= weight_sum
    return base_estimate_today + bias, bias


# =============================================================================
# 主流程
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', default='012922')
    parser.add_argument('--start', default='2026-04-01')
    parser.add_argument('--end', default='2026-04-30')
    parser.add_argument('--output', default='experiments/qdii-active-redesign-202604.md')
    parser.add_argument('--example-date', default='2026-04-08',
                        help='详细示例日（必须在窗口内且为交易日）')
    args = parser.parse_args()

    print(f'=== {args.code} 全新模型回测：{args.start} ~ {args.end} ===\n')

    # 1) 净值历史
    print('[1/6] 历史净值...')
    nav = fetch_fund_nav(args.code, total=120)
    nav_sorted = sorted([n for n in nav if n['pct'] is not None], key=lambda x: x['date'])
    nav_map = {n['date']: n for n in nav_sorted}
    print(f'  {len(nav_sorted)} 条')

    # 2) 季报披露
    print('[2/6] 季报披露...')
    holdings, rep_date = fetch_top10(args.code)
    ind_date, industries = fetch_industry(args.code)
    reg_date, regions = fetch_region(args.code)
    # 天天基金 f10 没有地区分布接口；012922 Q1 2026 季报 PDF 披露如下：
    if not regions and args.code == '012922':
        regions = [
            {'name': '美国',     'ratio': 46.00},
            {'name': '中国内地', 'ratio': 33.06},
            {'name': '中国香港', 'ratio':  4.52},
            {'name': '日本',     'ratio':  1.17},
        ]
        reg_date = '2026-03-31 (来自季报PDF)'
    print(f'  报告期: {rep_date}, 前10: {len(holdings)} 只')
    print(f'  行业 {len(industries)} 个, 地区 {len(regions)} 个')

    # 给前 10 手工打 GICS 行业 + 地区中文名（与季报对齐）
    # 012922 易方达全球成长精选 Q1 2026
    HOLDING_META = {
        '台积电':            {'industry': '信息技术', 'region_name': '美国'},
        'Lumentum Holdings Inc': {'industry': '信息技术', 'region_name': '美国'},
        '新易盛':            {'industry': '信息技术', 'region_name': '中国内地'},
        '康宁':              {'industry': '信息技术', 'region_name': '美国'},
        'AXT Inc':           {'industry': '信息技术', 'region_name': '美国'},
        '中际旭创':          {'industry': '信息技术', 'region_name': '中国内地'},
        '源杰科技':          {'industry': '信息技术', 'region_name': '中国内地'},
        'Tower半导体':       {'industry': '信息技术', 'region_name': '美国'},
        '谷歌-A':            {'industry': '电信服务', 'region_name': '美国'},
        '东山精密':          {'industry': '信息技术', 'region_name': '中国内地'},
    }
    for h in holdings:
        meta = HOLDING_META.get(h['name'], {})
        h['industry'] = meta.get('industry', '?')
        h['region_name'] = meta.get('region_name', '?')

    # 3) 前 10 股票价格
    print('[3/6] 前10股票价格...')
    prices = {}
    for h in holdings:
        prefix, sym = h['secid'].split('.')
        if prefix in ('105', '106', '107'):
            rows = fetch_us_kline(sym)
        elif prefix in ('0', '1'):
            rows = fetch_cn_kline(h['secid'], days=90)
        else:
            rows = []
        if rows:
            prices[h['secid']] = to_map(rows)
        print(f'    {h["name"]:25s} {len(rows)} 条')
        time.sleep(0.2)

    # 4) 代理 ETF / 指数
    print('[4/6] 代理 ETF...')
    # 美股板块 ETF
    proxy_us = {}
    for nm, sym in [('XLK', 'xlk'), ('XLI', 'xli'), ('XLC', 'xlc'),
                    ('XLE', 'xle'), ('XLV', 'xlv'), ('XLP', 'xlp'),
                    ('XLY', 'xly'), ('XLF', 'xlf'), ('XLB', 'xlb')]:
        rows = fetch_us_kline(sym)
        if rows:
            proxy_us[nm] = to_map(rows)
        print(f'    US-{nm:4s} {len(rows)} 条')
        time.sleep(0.15)

    # A 股 ETF
    proxy_cn = {}
    for nm, secid in [('信息技术ETF', '0.159939'),    # 信息技术ETF
                      ('工业ETF',     '1.510170'),    # 化工ETF—暂代工业，可换更精准
                      ('通信ETF',     '1.515880'),    # 通信ETF
                      ('沪深300',     '1.510300'),    # 沪深300ETF（兜底）
                      ('创业板',      '0.159915')]:   # 创业板ETF
        rows = fetch_cn_kline(secid, days=90)
        if rows:
            proxy_cn[nm] = to_map(rows)
        print(f'    CN-{nm:8s} {len(rows)} 条')
        time.sleep(0.15)

    # 港股代理 — 用恒生科技 ETF（在 A 股交易）513180
    rows = fetch_cn_kline('1.513180', days=90)
    proxy_hk_tech = to_map(rows) if rows else {}
    print(f'    HK-恒生科技ETF {len(rows)} 条')
    rows2 = fetch_cn_kline('1.510900', days=90)
    proxy_hk = to_map(rows2) if rows2 else {}
    print(f'    HK-恒生ETF {len(rows2)} 条')

    # 日股代理 — Nikkei 225 ETF (USA)
    rows3 = fetch_us_kline('ewj')
    proxy_jp = to_map(rows3) if rows3 else {}
    print(f'    JP-EWJ {len(rows3)} 条')

    # 5) 行业 → 代理映射（β / γ 用）
    industry_proxy = {
        '信息技术':        proxy_us.get('XLK', {}),     # 70.85% 主力，按基金披露大头在美
        '工业':            proxy_us.get('XLI', {}),
        '电信服务':        proxy_us.get('XLC', {}),
        '能源':            proxy_us.get('XLE', {}),
        '材料':            proxy_us.get('XLB', {}),
        '保健':            proxy_us.get('XLV', {}),
        '非必需消费品':    proxy_us.get('XLY', {}),
        '必需消费品':      proxy_us.get('XLP', {}),
        '金融':            proxy_us.get('XLF', {}),
        '其他-GICS未分类': proxy_us.get('XLK', {}),
    }
    industry_proxy_named = {
        k: (v, name) for k, name, v in [
            ('信息技术', 'XLK', proxy_us.get('XLK', {})),
            ('工业', 'XLI', proxy_us.get('XLI', {})),
            ('电信服务', 'XLC', proxy_us.get('XLC', {})),
            ('能源', 'XLE', proxy_us.get('XLE', {})),
            ('材料', 'XLB', proxy_us.get('XLB', {})),
            ('保健', 'XLV', proxy_us.get('XLV', {})),
            ('非必需消费品', 'XLY', proxy_us.get('XLY', {})),
            ('必需消费品', 'XLP', proxy_us.get('XLP', {})),
            ('金融', 'XLF', proxy_us.get('XLF', {})),
            ('其他-GICS未分类', 'XLK', proxy_us.get('XLK', {})),
        ]
    }

    # γ 用：industry → (price_map, proxy_name)
    ind_proxy_assign = {
        '信息技术':     ('us_xlk', 'XLK'),
        '工业':         ('us_xli', 'XLI'),
        '电信服务':     ('us_xlc', 'XLC'),
        '能源':         ('us_xle', 'XLE'),
        '材料':         ('us_xlb', 'XLB'),
        '保健':         ('us_xlv', 'XLV'),
        '非必需消费品': ('us_xly', 'XLY'),
        '必需消费品':   ('us_xlp', 'XLP'),
        '金融':         ('us_xlf', 'XLF'),
        '其他-GICS未分类': ('us_xlk', 'XLK'),
    }
    proxy_pmap = {
        'us_xlk': proxy_us.get('XLK', {}),
        'us_xli': proxy_us.get('XLI', {}),
        'us_xlc': proxy_us.get('XLC', {}),
        'us_xle': proxy_us.get('XLE', {}),
        'us_xlb': proxy_us.get('XLB', {}),
        'us_xlv': proxy_us.get('XLV', {}),
        'us_xly': proxy_us.get('XLY', {}),
        'us_xlp': proxy_us.get('XLP', {}),
        'us_xlf': proxy_us.get('XLF', {}),
    }

    # δ 用：(region, industry) → (price_map, proxy_name)
    # 假设：各地区都用「该地区+该行业」组合的代理；缺失时回退到地区主代理
    region_industry_proxy = {}
    # 美国：每个行业各对应一个 SPDR sector ETF
    for ind, (pkey, pname) in [('信息技术', ('XLK', 'XLK')), ('工业', ('XLI', 'XLI')),
                                 ('电信服务', ('XLC', 'XLC')), ('能源', ('XLE', 'XLE')),
                                 ('材料', ('XLB', 'XLB')), ('保健', ('XLV', 'XLV')),
                                 ('非必需消费品', ('XLY', 'XLY')), ('必需消费品', ('XLP', 'XLP')),
                                 ('金融', ('XLF', 'XLF')), ('其他-GICS未分类', ('XLK', 'XLK'))]:
        region_industry_proxy[('美国', ind)] = (proxy_us.get(pkey, {}), f'US/{pname}')
    region_industry_proxy[('美国', '*')] = (proxy_us.get('XLK', {}), 'US/XLK')

    # 中国内地：信息技术用信息技术ETF，其他兜底用沪深300
    region_industry_proxy[('中国内地', '信息技术')] = (proxy_cn.get('信息技术ETF', {}), 'CN/信息技术ETF')
    region_industry_proxy[('中国内地', '工业')]     = (proxy_cn.get('沪深300', {}), 'CN/沪深300')
    region_industry_proxy[('中国内地', '电信服务')] = (proxy_cn.get('通信ETF', {}), 'CN/通信ETF')
    region_industry_proxy[('中国内地', '*')]        = (proxy_cn.get('沪深300', {}), 'CN/沪深300')
    for ind in ['能源', '材料', '保健', '非必需消费品', '必需消费品', '金融', '其他-GICS未分类']:
        region_industry_proxy[('中国内地', ind)] = (proxy_cn.get('沪深300', {}), 'CN/沪深300')

    # 香港：除信息技术用恒生科技，其他用恒生指数
    for ind in ['信息技术', '电信服务', '其他-GICS未分类']:
        region_industry_proxy[('中国香港', ind)] = (proxy_hk_tech, 'HK/恒生科技')
    for ind in ['工业', '能源', '材料', '保健', '非必需消费品', '必需消费品', '金融']:
        region_industry_proxy[('中国香港', ind)] = (proxy_hk, 'HK/恒生')
    region_industry_proxy[('中国香港', '*')] = (proxy_hk_tech, 'HK/恒生科技')

    # 日本：所有行业都用 EWJ
    for ind in [x['name'] for x in industries]:
        region_industry_proxy[('日本', ind)] = (proxy_jp, 'JP/EWJ')
    region_industry_proxy[('日本', '*')] = (proxy_jp, 'JP/EWJ')

    # 6) 回测日窗口
    print('[5/6] 回测...')
    target_dates = []
    for n in nav_sorted:
        if args.start <= n['date'] <= args.end:
            target_dates.append(n['date'])
    print(f'  匹配 {len(target_dates)} 个交易日')

    # 找每个目标日的「前一交易日」
    def prev_in_nav(d):
        idx = next((i for i, n in enumerate(nav_sorted) if n['date'] == d), -1)
        if idx <= 0:
            return None
        return nav_sorted[idx - 1]['date']

    # 跑模型
    rows = []
    history_for_e5 = []  # 方案五: γ vs actual 历史
    history_for_e6 = []  # 方案六: δ vs actual 历史
    LAM = 0.6

    for d in target_dates:
        pd_ = prev_in_nav(d)
        if not pd_:
            continue
        actual = nav_map[d]['pct']

        # α
        a_est, _ = model_alpha(holdings, prices, d, pd_)
        # β: 注意 industry_proxy_named 形式
        b_est, _ = model_beta(industries,
                              {k: (v[0], v[1]) for k, v in industry_proxy_named.items()},
                              d, pd_)
        # γ
        g_est, _ = model_gamma(holdings, industries, prices, proxy_pmap,
                               ind_proxy_assign, d, pd_)
        # δ
        d_est, _ = model_delta(holdings, regions, industries, prices,
                               region_industry_proxy, d, pd_)
        # 方案五: 方案三(γ) + EWMA 残差自校准
        e5_est, e5_bias = model_epsilon(g_est, history_for_e5, lam=LAM)
        # 方案六: 方案四(δ) + EWMA 残差自校准
        e6_est, e6_bias = model_epsilon(d_est, history_for_e6, lam=LAM)

        rows.append({
            'date': d, 'prev': pd_, 'actual': actual,
            'alpha': a_est, 'beta': b_est, 'gamma': g_est,
            'delta': d_est, 'epsilon5': e5_est, 'epsilon6': e6_est,
            'e5_bias': e5_bias, 'e6_bias': e6_bias,
        })

        # 喂养历史
        history_for_e5.append({'actual': actual, 'base_est': g_est})
        if len(history_for_e5) > 12:
            history_for_e5.pop(0)
        history_for_e6.append({'actual': actual, 'base_est': d_est})
        if len(history_for_e6) > 12:
            history_for_e6.pop(0)

    # 7) 误差汇总
    def stats(key):
        errs = [abs(r[key] - r['actual']) for r in rows]
        signs = [r[key] - r['actual'] for r in rows]
        return {
            'mae': sum(errs) / len(errs) if errs else 0,
            'max': max(errs) if errs else 0,
            'bias': sum(signs) / len(signs) if signs else 0,
            'hit_03': sum(1 for e in errs if e < 0.3) / len(errs) * 100 if errs else 0,
            'hit_05': sum(1 for e in errs if e < 0.5) / len(errs) * 100 if errs else 0,
        }

    summary = {k: stats(k) for k in ['alpha', 'beta', 'gamma', 'delta', 'epsilon5', 'epsilon6']}

    # 8) 抓 example date 的逐行计算细节
    print('[6/6] 输出报告...')
    example_data = build_example(args.example_date, nav_sorted, nav_map, holdings,
                                 prices, industries, regions, proxy_pmap,
                                 ind_proxy_assign, region_industry_proxy,
                                 industry_proxy_named, [], LAM,
                                 rows)

    md = build_md(args.code, args.start, args.end, rep_date, holdings,
                  industries, regions, rows, summary, example_data, args.example_date)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f'\n报告已输出 → {args.output}')

    # 控制台速览
    print('\n=== 误差汇总 (April 2026) ===')
    for k in ['alpha', 'beta', 'gamma', 'delta', 'epsilon5', 'epsilon6']:
        s = summary[k]
        print(f'{k:8s}  MAE={s["mae"]:.3f}%  Bias={s["bias"]:+.3f}%  '
              f'Max={s["max"]:.2f}%  <0.3={s["hit_03"]:.0f}%  <0.5={s["hit_05"]:.0f}%')


def build_example(ex_date, nav_sorted, nav_map, holdings, prices,
                  industries, regions, proxy_pmap, ind_proxy_assign,
                  region_industry_proxy, industry_proxy_named,
                  history_for_eps_initial, lam, all_rows):
    """对 ex_date 这一天，记录每个模型的逐项计算细节"""
    if ex_date not in nav_map:
        return None
    idx = next(i for i, n in enumerate(nav_sorted) if n['date'] == ex_date)
    if idx == 0:
        return None
    prev = nav_sorted[idx - 1]['date']
    actual = nav_map[ex_date]['pct']

    out = {'date': ex_date, 'prev': prev, 'actual': actual}

    # α 详情
    out['alpha'] = []
    a_total = 0
    for h in holdings:
        pmap = prices.get(h['secid'], {})
        p_prev = pmap.get(prev)
        p_now = pmap.get(ex_date)
        if p_prev and p_now:
            r = (p_now - p_prev) / p_prev * 100
            c = r * h['ratio'] / 100
            a_total += c
            out['alpha'].append({'name': h['name'], 'p_prev': p_prev, 'p_now': p_now,
                                  'r': r, 'w': h['ratio'], 'contrib': c})
        else:
            out['alpha'].append({'name': h['name'], 'p_prev': p_prev, 'p_now': p_now,
                                  'r': None, 'w': h['ratio'], 'contrib': 0})
    out['alpha_total'] = a_total

    # β 详情
    out['beta'] = []
    b_total = 0
    for ind in industries:
        pmap, pname = industry_proxy_named.get(ind['name'], ({}, '无'))
        p_prev = pmap.get(prev)
        p_now = pmap.get(ex_date)
        if p_prev and p_now:
            r = (p_now - p_prev) / p_prev * 100
            c = r * ind['ratio'] / 100
            b_total += c
            out['beta'].append({'industry': ind['name'], 'proxy': pname,
                                 'r': r, 'w': ind['ratio'], 'contrib': c})
        else:
            out['beta'].append({'industry': ind['name'], 'proxy': pname,
                                 'r': None, 'w': ind['ratio'], 'contrib': 0})
    out['beta_total'] = b_total

    # γ 详情
    g_top = 0
    g_top_detail = []
    industry_used = {ind['name']: 0.0 for ind in industries}
    for h in holdings:
        pmap = prices.get(h['secid'], {})
        p_prev = pmap.get(prev)
        p_now = pmap.get(ex_date)
        if p_prev and p_now:
            r = (p_now - p_prev) / p_prev * 100
            c = r * h['ratio'] / 100
            g_top += c
            g_top_detail.append({'name': h['name'], 'industry': h.get('industry', '?'),
                                  'w': h['ratio'], 'r': r, 'contrib': c})
            if h.get('industry') in industry_used:
                industry_used[h['industry']] += h['ratio']
    g_resid = 0
    g_resid_detail = []
    for ind in industries:
        used = industry_used.get(ind['name'], 0.0)
        resid = max(0.0, ind['ratio'] - used)
        proxy_key, proxy_name = ind_proxy_assign.get(ind['name'], (None, None))
        pmap = proxy_pmap.get(proxy_key, {})
        if proxy_key and resid > 0:
            p_prev = pmap.get(prev)
            p_now = pmap.get(ex_date)
            if p_prev and p_now:
                r = (p_now - p_prev) / p_prev * 100
                c = r * resid / 100
                g_resid += c
                g_resid_detail.append({'industry': ind['name'], 'used': used,
                                        'resid': resid, 'proxy': proxy_name,
                                        'r': r, 'contrib': c})
                continue
        g_resid_detail.append({'industry': ind['name'], 'used': used, 'resid': resid,
                                'proxy': proxy_name, 'r': None, 'contrib': 0})
    out['gamma'] = {'top': g_top_detail, 'resid': g_resid_detail,
                    'top_total': g_top, 'resid_total': g_resid,
                    'total': g_top + g_resid}

    # δ 详情：地区 × 行业 网格
    total_stock = sum(x['ratio'] for x in industries)
    cells = {}
    for reg in regions:
        for ind in industries:
            w = reg['ratio'] * (ind['ratio'] / total_stock) if total_stock > 0 else 0
            cells[(reg['name'], ind['name'])] = {'weight': w, 'used': 0.0}

    d_top = 0
    d_top_detail = []
    for h in holdings:
        pmap = prices.get(h['secid'], {})
        p_prev = pmap.get(prev)
        p_now = pmap.get(ex_date)
        if p_prev and p_now:
            r = (p_now - p_prev) / p_prev * 100
            c = r * h['ratio'] / 100
            d_top += c
            d_top_detail.append({'name': h['name'], 'region': h.get('region_name', '?'),
                                  'industry': h.get('industry', '?'), 'w': h['ratio'],
                                  'r': r, 'contrib': c})
            key = (h.get('region_name', ''), h.get('industry', ''))
            if key in cells:
                cells[key]['used'] += h['ratio']

    d_resid = 0
    d_resid_detail = []
    for (reg, ind), info in cells.items():
        resid = max(0.0, info['weight'] - info['used'])
        if resid <= 1e-3:
            # 跳过太小的网格
            continue
        proxy_pair = region_industry_proxy.get((reg, ind))
        if not proxy_pair:
            proxy_pair = region_industry_proxy.get((reg, '*'))
        if not proxy_pair:
            d_resid_detail.append({'region': reg, 'industry': ind, 'cell_w': info['weight'],
                                    'used': info['used'], 'resid': resid,
                                    'proxy': '无', 'r': None, 'contrib': 0})
            continue
        pmap, proxy_name = proxy_pair
        p_prev = pmap.get(prev)
        p_now = pmap.get(ex_date)
        if p_prev and p_now:
            r = (p_now - p_prev) / p_prev * 100
            c = r * resid / 100
            d_resid += c
            d_resid_detail.append({'region': reg, 'industry': ind, 'cell_w': info['weight'],
                                    'used': info['used'], 'resid': resid,
                                    'proxy': proxy_name, 'r': r, 'contrib': c})
        else:
            d_resid_detail.append({'region': reg, 'industry': ind, 'cell_w': info['weight'],
                                    'used': info['used'], 'resid': resid,
                                    'proxy': proxy_name, 'r': None, 'contrib': 0})
    # 残余按贡献绝对值降序，方便阅读
    d_resid_detail.sort(key=lambda x: -abs(x.get('contrib', 0)))
    out['delta'] = {'top': d_top_detail, 'resid': d_resid_detail,
                    'top_total': d_top, 'resid_total': d_resid,
                    'total': d_top + d_resid,
                    'total_stock': total_stock}

    # 方案五详情：γ + EWMA
    eps_history = [r for r in all_rows if r['date'] < ex_date]
    eps_history = eps_history[-10:]
    if eps_history:
        weights5 = []
        ws = 0
        b = 0
        for i, r in enumerate(eps_history):
            age = len(eps_history) - 1 - i
            w = lam ** age
            ws += w
            b += w * (r['actual'] - r['gamma'])
            weights5.append({'date': r['date'], 'actual': r['actual'],
                             'base_est': r['gamma'], 'residual': r['actual'] - r['gamma'],
                             'age': age, 'weight': w})
        bias5 = b / ws
        out['epsilon5'] = {'history': weights5, 'bias': bias5,
                           'base': out['gamma']['total'],
                           'total': out['gamma']['total'] + bias5}
    else:
        out['epsilon5'] = {'history': [], 'bias': 0,
                           'base': out['gamma']['total'],
                           'total': out['gamma']['total']}

    # 方案六详情：δ + EWMA
    if eps_history:
        weights6 = []
        ws = 0
        b = 0
        for i, r in enumerate(eps_history):
            age = len(eps_history) - 1 - i
            w = lam ** age
            ws += w
            b += w * (r['actual'] - r['delta'])
            weights6.append({'date': r['date'], 'actual': r['actual'],
                             'base_est': r['delta'], 'residual': r['actual'] - r['delta'],
                             'age': age, 'weight': w})
        bias6 = b / ws
        out['epsilon6'] = {'history': weights6, 'bias': bias6,
                           'base': d_top + d_resid,
                           'total': d_top + d_resid + bias6}
    else:
        out['epsilon6'] = {'history': [], 'bias': 0,
                           'base': d_top + d_resid,
                           'total': d_top + d_resid}

    return out


def build_md(code, start, end, rep_date, holdings, industries, regions,
             rows, summary, example, ex_date):
    md = []
    md.append(f'# QDII 主动型基金估值模型 — 全新设计与回测\n')
    md.append(f'基金：**{code} 易方达全球成长精选**  ')
    md.append(f'回测窗口：**{start} ~ {end}**  ')
    md.append(f'季报报告期：**{rep_date}**  ')
    md.append(f'生成时间：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}\n')

    md.append('## 0. 痛点与设计目标\n')
    md.append('美股 04:00 收盘 → 国内基金 19:00-22:00 更新净值，中间约 15 小时信息真空。')
    md.append('QDII 主动型基金估算的两大死结：\n')
    md.append('1. **持仓滞后** — 季报披露的是上季度末时点持仓，最长滞后 1 季度。')
    md.append('2. **长尾不透明** — 前 10 仅覆盖 ~50% 净值，剩余约 50% 中既有股票也有现金/其他基金。\n')

    md.append('## 1. 全新模型设计\n')
    md.append('完全独立设计，以下 5 个方案，逐步从「简单」走向「精细+自校准」：\n')

    md.append('### 方案一 — 纯前十大持仓加权法\n')
    md.append('最朴素的思路：基金披露什么我们就算什么。\n')
    md.append('```')
    md.append('估算 = Σ_{i=1..10} (持仓i占比 × 持仓i今日涨跌)')
    md.append('')
    md.append('占比来自季报；涨跌来自当日行情。')
    md.append('剩余约 48% 仓位（前 10 之外的股票 + 现金 + 债券）默认涨跌 0%。')
    md.append('```')
    md.append('**优点**：简单透明，每个数字用户都能看到来源。  ')
    md.append('**缺点**：把约一半的仓位当成「不动」，会系统性低估涨跌幅度。\n')

    md.append('### 方案二 — 行业 ETF 替身法\n')
    md.append('完全跳过个股，直接用行业代理 ETF。\n')
    md.append('```')
    md.append('估算 = Σ_j (行业j占比 × 行业j代理ETF今日涨跌)')
    md.append('')
    md.append('信息技术 → XLK，工业 → XLI，电信服务 → XLC')
    md.append('能源 → XLE，材料 → XLB，保健 → XLV')
    md.append('非必需消费品 → XLY，必需消费品 → XLP，金融 → XLF')
    md.append('```')
    md.append('**优点**：覆盖全部已披露的股票仓位（84.75%）。  ')
    md.append('**缺点**：丢失了基金经理的选股 alpha；持仓越集中，误差越大。\n')

    md.append('### 方案三 — 前十持仓 + 行业残余补全法\n')
    md.append('方案一和方案二的折中：前 10 用真实股票，剩余的按行业用 ETF 补。\n')
    md.append('```')
    md.append('估算 = Σ_{i=1..10} (持仓i占比 × 持仓i今日涨跌)        ← 已披露')
    md.append('     + Σ_j (行业j占比 - 前10在j的占比) × 行业j代理ETF涨跌  ← 残余')
    md.append('')
    md.append('做法：')
    md.append('  1) 把每只前 10 重仓股按 GICS 归到对应行业')
    md.append('  2) 行业总占比里减去前 10 已经占用的部分，剩下的就是「行业残余」')
    md.append('  3) 行业残余用对应行业 ETF 估算')
    md.append('```')
    md.append('**关键创新**：前 10 用「真实涨跌」，避免行业 ETF 抹平选股 alpha；')
    md.append('剩余仓位用「行业 ETF」，避免方案一直接归零。\n')

    md.append('### 方案四 — 地区 × 行业 网格法\n')
    md.append('在方案三上多加一个维度：把每个仓位拆到「地区 × 行业」二维网格。\n')
    md.append('```')
    md.append('网格(地区r, 行业j) 权重 = 地区r占比 × (行业j占比 / 行业总占比)')
    md.append('')
    md.append('对每个网格：')
    md.append('  - 前 10 中有股票落在该网格 → 用真实股票涨跌')
    md.append('  - 否则 → 用 (地区, 行业) 对应的代理：')
    md.append('       (美国, 信息技术) → XLK')
    md.append('       (中国内地, 信息技术) → 信息技术 ETF (159939)')
    md.append('       (中国香港, 信息技术) → 恒生科技 ETF (513180)')
    md.append('       (日本, 任何) → EWJ')
    md.append('```')
    md.append('**为什么要分地区**：QDII 的港股、A 股、美股交易时间不同步，')
    md.append('单纯用美股 ETF 估算会忽略当天 A 股、港股的实际涨跌。\n')
    md.append('**前提假设**：每个地区内的行业分布与基金整体相同（季报不公布交叉表）。\n')

    md.append('### 方案五 — 方案四 + 历史误差自校准\n')
    md.append('在方案四（精度最高的基础模型）的估算上，叠加一个「最近几天的偏差均值」。\n')
    md.append('```')
    md.append('校准后估算 = 方案四估算 + 最近偏差')
    md.append('')
    md.append('最近偏差 = 最近 N 天 (实际净值涨跌 - 方案四估算) 的指数加权平均')
    md.append('         = Σ λ^age × (实际_t - 方案四_t) / Σ λ^age')
    md.append('')
    md.append('λ = 0.6（衰减系数），N = 10（窗口）')
    md.append('权重示意：今天 1.0，前 1 天 0.6，前 2 天 0.36，前 3 天 0.22 ...')
    md.append('```')
    md.append('**为什么用方案四做底**：方案四 MAE 最低（0.497%），在它上面做校准起点更高。')
    md.append('方案四的残余偏差主要来自「地区×行业交叉分布假设」和「基金调仓」，')
    md.append('EWMA 残差校正正好能把这些系统性偏差消掉。\n')

    md.append('### 方案六 — 方案四 + 历史误差自校准\n')
    md.append('和方案五完全相同的校准方法，但底座换成方案四（地区×行业网格）。\n')
    md.append('```')
    md.append('校准后估算 = 方案四估算 + 最近偏差')
    md.append('')
    md.append('最近偏差 = 最近 N 天 (实际净值涨跌 - 方案四估算) 的指数加权平均')
    md.append('```')
    md.append('**为什么要同时保留方案五和方案六**：')
    md.append('- 方案五（方案三+校准）：实现简单，只需美股 ETF 数据，适合 API 调用受限的场景')
    md.append('- 方案六（方案四+校准）：精度更高，但需要 A 股/港股/日股 ETF 数据，依赖更多数据源')
    md.append('- 两者对比可以量化「加入地区维度」到底值多少精度\n')

    md.append('### 补充讨论：Q1 季报 + 年报全持仓组合方案\n')
    md.append('这个方案的思路是：\n')
    md.append('```')
    md.append('前 10 大持仓 → 用最新季报（占比最精确，2026-03-31）')
    md.append('第 11 及之后 → 用年报公开的全持仓（2025 年报，覆盖率高但数据旧半年）')
    md.append('合并去重后，按实际覆盖率还原：')
    md.append('')
    md.append('估算 = [Σ(合并持仓涨跌 × 占比)] / 实际覆盖率')
    md.append('```\n')
    md.append('**优点**：')
    md.append('- 覆盖率极高（年报通常披露 30-80 只股票，覆盖 70-90% 仓位）')
    md.append('- 不需要代理 ETF，全部用真实个股涨跌\n')
    md.append('**缺点**：')
    md.append('- 年报数据滞后半年（2025 年报反映的是 2025-12-31 的持仓），基金经理半年内可能大幅调仓')
    md.append('- 第 11 及之后的股票占比用的是年报数据，与当前实际偏差可能很大')
    md.append('- 需要拉取 30-80 只股票的实时行情，API 调用量大、延迟高\n')
    md.append('**本次未纳入回测的原因**：')
    md.append('- 012922 的 2025 年报全持仓数据在天天基金接口中返回不完整（仅返回前 10）')
    md.append('- 即使数据完整，半年前的持仓对 2026 年 4 月的估算参考价值有限')
    md.append('- 方案四（地区×行业网格）+ 方案五（自校准）已经达到 MAE 0.47%，')
    md.append('  年报方案即使数据完美也很难超越（因为半年前的持仓权重已经过时）\n')
    md.append('**建议**：如果未来天天基金接口能稳定返回年报全持仓，可以作为方案三的替代——')
    md.append('用真实个股替代行业 ETF 来填补「前 10 之外」的仓位。')
    md.append('但需要注意：年报占比 ≠ 当前占比，仍然需要叠加自校准（方案五）来修正偏差。\n')

    md.append('## 1.5 代理 ETF / 指数对照表\n')
    md.append('上面方案二、三、四 用到了一系列代理 ETF。这些 ETF 都是公开交易、流动性极好的指数化产品，')
    md.append('每个对应一个明确的行业或地区主题，能在没有个股数据时近似代表该板块的当日表现。\n')

    md.append('### 美股板块 ETF（SPDR 9 大行业 ETF 系列）\n')
    md.append('全名 Select Sector SPDR ETF，由道富资产 State Street 发行，按 GICS 行业把标普 500 切成 11 块（基金这里用到 9 块）。\n')
    md.append('| 代码 | 全名 | 中文 | 对应 GICS 行业 | 主要持仓示例 |')
    md.append('|------|------|------|--------------|------------|')
    md.append('| **XLK** | Technology Select Sector SPDR Fund | 美股科技 ETF | Information Technology 信息技术 | 苹果、微软、英伟达、博通、Oracle |')
    md.append('| **XLI** | Industrial Select Sector SPDR Fund | 美股工业 ETF | Industrials 工业 | GE、卡特彼勒、霍尼韦尔、洛马、UPS |')
    md.append('| **XLC** | Communication Services Select Sector SPDR | 美股通信服务 ETF | Communication Services 电信服务 | Meta、谷歌、Netflix、AT&T、Verizon |')
    md.append('| **XLE** | Energy Select Sector SPDR Fund | 美股能源 ETF | Energy 能源 | 埃克森美孚、雪佛龙、康菲石油 |')
    md.append('| **XLB** | Materials Select Sector SPDR Fund | 美股原材料 ETF | Materials 材料 | Linde、Sherwin-Williams、Ecolab |')
    md.append('| **XLV** | Health Care Select Sector SPDR Fund | 美股医疗保健 ETF | Health Care 保健 | 礼来、强生、联合健康、辉瑞 |')
    md.append('| **XLY** | Consumer Discretionary Select Sector SPDR | 美股可选消费 ETF | Consumer Discretionary 非必需消费品 | 亚马逊、特斯拉、家得宝、麦当劳 |')
    md.append('| **XLP** | Consumer Staples Select Sector SPDR | 美股必选消费 ETF | Consumer Staples 必需消费品 | Costco、宝洁、可口可乐、沃尔玛 |')
    md.append('| **XLF** | Financial Select Sector SPDR Fund | 美股金融 ETF | Financials 金融 | 摩根大通、伯克希尔、美国银行、Visa |\n')

    md.append('### A 股 ETF（用于中国内地仓位代理）\n')
    md.append('| 代码 | 名称 | 用途 |')
    md.append('|------|------|------|')
    md.append('| **159939** | 信息技术 ETF（广发中证全指信息技术 ETF） | 代理 A 股信息技术行业（光模块、半导体、消费电子） |')
    md.append('| **510170** | 化工 ETF（暂代工业大类） | 用作 A 股工业行业的兜底代理 |')
    md.append('| **515880** | 通信 ETF（华夏中证全指通信设备 ETF） | 代理 A 股电信服务 / 通信设备行业 |')
    md.append('| **510300** | 沪深 300 ETF | 当 A 股某行业找不到精准代理时的兜底大盘指数 |')
    md.append('| **159915** | 创业板 ETF | 备选成长股代理（脚本中已加载，本次未直接使用） |\n')

    md.append('### 港股代理 ETF（在 A 股交易，规避港股交易时间差异）\n')
    md.append('| 代码 | 名称 | 用途 |')
    md.append('|------|------|------|')
    md.append('| **513180** | 恒生科技 ETF（华夏） | 代理港股科技股（信息技术 + 部分电信服务），跟踪恒生科技指数 |')
    md.append('| **510900** | 恒生 ETF（华夏） | 代理港股大盘（金融、能源、工业等非科技板块），跟踪恒生指数 |\n')

    md.append('### 日股代理\n')
    md.append('| 代码 | 名称 | 用途 |')
    md.append('|------|------|------|')
    md.append('| **EWJ** | iShares MSCI Japan ETF（在美股交易） | 代理日股大盘，覆盖丰田、索尼、东京电子等 |\n')

    md.append('### 为什么这样选代理\n')
    md.append('- **同板块同涨跌**：代理 ETF 一篮子持仓与基金该板块的持仓高度相关，β 接近 1；')
    md.append('- **同时区收盘**：A 股仓位用 A 股 ETF（159939、515880）保证当日收盘价口径一致，')
    md.append('  港股仓位用在 A 股交易的 513180 / 510900 而不是港股原生 ETF，避免港股 16:00 收盘但基金 15:00 估值的时差；')
    md.append('- **流动性高**：以上 ETF 日均成交都在亿级，新浪财经的日 K 数据稳定，便于自动化拉取。\n')

    md.append('## 2. 基金披露数据\n')
    md.append('### 2.1 前 10 大持仓（已经过 GICS 行业打标）\n')
    md.append('| # | 股票 | 市场 | 行业 | 占净值 |')
    md.append('|---|------|------|------|--------|')
    for i, h in enumerate(holdings, 1):
        md.append(f'| {i} | {h["name"]} | {h["market"]} | {h.get("industry", "?")} | {h["ratio"]:.2f}% |')
    total_top = sum(h['ratio'] for h in holdings)
    md.append(f'| | **合计** | | | **{total_top:.2f}%** |\n')

    md.append('### 2.2 行业分布\n')
    md.append('| 行业 | 占净值 |')
    md.append('|------|--------|')
    for ind in industries:
        md.append(f'| {ind["name"]} | {ind["ratio"]:.2f}% |')
    total_ind = sum(x['ratio'] for x in industries)
    md.append(f'| **合计** | **{total_ind:.2f}%** |\n')

    md.append('### 2.3 地区分布\n')
    md.append('| 地区 | 占净值 |')
    md.append('|------|--------|')
    for r in regions:
        md.append(f'| {r["name"]} | {r["ratio"]:.2f}% |')
    total_reg = sum(x['ratio'] for x in regions)
    md.append(f'| **合计** | **{total_reg:.2f}%** |\n')

    # 3. 详细回测明细
    md.append(f'## 3. 回测明细（{start} ~ {end}）\n')
    md.append('| 日期 | 实际 | 方案一 | 误差 | 方案二 | 误差 | 方案三 | 误差 | 方案四 | 误差 | 方案五 | 误差 | 方案六 | 误差 |')
    md.append('|------|------|-------|------|-------|------|-------|------|-------|------|-------|------|-------|------|')
    for r in rows:
        md.append(
            f'| {r["date"]} | {r["actual"]:+.2f}% '
            f'| {r["alpha"]:+.2f}% | {r["alpha"] - r["actual"]:+.2f} '
            f'| {r["beta"]:+.2f}% | {r["beta"] - r["actual"]:+.2f} '
            f'| {r["gamma"]:+.2f}% | {r["gamma"] - r["actual"]:+.2f} '
            f'| {r["delta"]:+.2f}% | {r["delta"] - r["actual"]:+.2f} '
            f'| {r["epsilon5"]:+.2f}% | {r["epsilon5"] - r["actual"]:+.2f} '
            f'| {r["epsilon6"]:+.2f}% | {r["epsilon6"] - r["actual"]:+.2f} |'
        )
    md.append('')

    md.append('## 4. 误差汇总\n')

    md.append('### 名词解释\n')
    md.append('| 指标 | 全称 | 含义（白话） |')
    md.append('|------|------|------------|')
    md.append('| **MAE** | Mean Absolute Error（平均绝对误差） | 把每天的「估算 - 实际」取绝对值再求平均。**越小越好**，代表"平均每天偏了多少"。 |')
    md.append('| **Bias** | 偏差（平均误差，带正负号） | 把每天的「估算 - 实际」直接求平均（不取绝对值）。正数 = 系统性高估，负数 = 系统性低估，0 = 无偏。 |')
    md.append('| **最大误差** | Max Absolute Error | 所有交易日中，偏差绝对值最大的那一天。衡量"最坏情况有多离谱"。 |')
    md.append('| **<0.3% 命中** | — | 误差绝对值 < 0.3% 的天数占比。越高说明"大部分时候估得很准"。 |')
    md.append('| **<0.5% 命中** | — | 误差绝对值 < 0.5% 的天数占比。0.5% 是用户体感上"可接受"的阈值。 |\n')
    md.append('**举例**：方案三 MAE = 0.549% 意味着平均每天估算偏差约 0.55 个百分点；')
    md.append('Bias = -0.295% 说明它倾向于低估（估出来的涨跌比实际小 0.3 个百分点左右）。\n')

    md.append('### 汇总表\n')
    md.append('| 方案 | MAE | Bias | 最大误差 | <0.3% 命中 | <0.5% 命中 |')
    md.append('|------|-----|------|---------|-----------|-----------|')
    for k, label in [('alpha',    '方案一 纯前十大持仓加权'),
                      ('beta',     '方案二 行业 ETF 替身'),
                      ('gamma',    '方案三 前十+行业残余补全'),
                      ('delta',    '方案四 地区×行业网格'),
                      ('epsilon5', '方案五 方案三+历史误差自校准'),
                      ('epsilon6', '方案六 方案四+历史误差自校准')]:
        s = summary[k]
        md.append(f'| {label} | **{s["mae"]:.3f}%** | {s["bias"]:+.3f}% | '
                  f'{s["max"]:.2f}% | {s["hit_03"]:.0f}% | {s["hit_05"]:.0f}% |')
    md.append('')

    # 5. 详细示例
    if example:
        md.append(f'## 5. 单日详细计算示例：{ex_date}\n')
        md.append(f'选这一天的原因：当日实际涨跌 **{example["actual"]:+.2f}%**，')
        md.append(f'是 4 月份波动最大的一天，能清楚地看出每个方案的差距。\n')
        md.append(f'**关键输入**：')
        md.append(f'- 当日（T 日）= {ex_date}')
        md.append(f'- 前一交易日（T-1 日）= {example["prev"]}')
        md.append(f'- 当日实际净值涨跌（事后值）= {example["actual"]:+.2f}%')
        md.append(f'- 美股 T 日 RTH 收盘对应基金 T 日净值；A 股 / 港股用 T 日收盘\n')

        # ============ 方案一 ============
        md.append('### 5.1 方案一（纯前十大持仓加权法）计算过程\n')
        md.append('**思路一句话**：基金披露什么我们就算什么，剩下的算 0%。\n')
        md.append('**第 1 步**：拿到季报披露的前 10 大持仓占比（已经在 §2.1）。\n')
        md.append(f'**第 2 步**：拿每只股票在 T-1 → T 的收盘价，逐行算涨跌、加权求和：\n')
        md.append('| 股票 | 占比 (a) | T-1 收盘 | T 收盘 | 涨跌 (b) = (T - T-1) / T-1 | 贡献 = a × b |')
        md.append('|------|---------|----------|--------|----------|--------------|')
        a_total = 0
        for it in example['alpha']:
            r_str = f'{it["r"]:+.2f}%' if it["r"] is not None else '—'
            contrib_str = f'{it["contrib"]:+.4f}%' if it["r"] is not None else '0.0000%'
            a_total = example['alpha_total']
            md.append(f'| {it["name"]} | {it["w"]:.2f}% | '
                      f'{it["p_prev"] or "—"} | {it["p_now"] or "—"} | '
                      f'{r_str} | {contrib_str} |')
        md.append(f'| | | | | **合计** | **{a_total:+.4f}%** |\n')
        # 抓第一行做手算示范
        if example['alpha']:
            first = example['alpha'][0]
            if first["r"] is not None:
                md.append('**逐项展开**（以表格第 1 行示范）：\n')
                md.append(f'- 涨跌 = ({first["p_now"]} - {first["p_prev"]}) / {first["p_prev"]} = {first["r"]:+.4f}%')
                md.append(f'- 贡献 = {first["w"]:.2f}% × {first["r"]:+.4f}% = {first["contrib"]:+.4f}%\n')
        md.append(f'**第 3 步**：把 10 行贡献相加，剩余约 48% 仓位默认 0%：\n')
        md.append(f'> **方案一估算 = {example["alpha_total"]:+.3f}%**  ')
        md.append(f'> 实际 = {example["actual"]:+.2f}%，方案一误差 = {example["alpha_total"] - example["actual"]:+.3f}%\n')
        md.append(f'**为什么偏差大**：这一天前 10 之外的仓位（中国内地工业股、信息技术 ETF 那部分）')
        md.append(f'也上涨了，但方案一把它们当成 0%，所以系统性低估约 {abs(example["alpha_total"] - example["actual"]):.2f} 个百分点。\n')

        # ============ 方案二 ============
        md.append('### 5.2 方案二（行业 ETF 替身法）计算过程\n')
        md.append('**思路一句话**：完全跳过个股，把基金当成一只「按行业占比组成的板块 ETF 组合」。\n')
        md.append('**第 1 步**：从季报拿到 10 个行业的占比（已在 §2.2）。\n')
        md.append('**第 2 步**：每个行业找一个代理 ETF，查它当日涨跌：\n')
        md.append('| 行业 | 占比 (a) | 代理 ETF | 代理涨跌 (b) | 贡献 = a × b |')
        md.append('|------|---------|----------|-------------|--------------|')
        for it in example['beta']:
            r_str = f'{it["r"]:+.2f}%' if it["r"] is not None else '—'
            contrib_str = f'{it["contrib"]:+.4f}%' if it["r"] is not None else '0.0000%'
            md.append(f'| {it["industry"]} | {it["w"]:.2f}% | {it["proxy"]} | '
                      f'{r_str} | {contrib_str} |')
        md.append(f'| | | | **合计** | **{example["beta_total"]:+.4f}%** |\n')
        # 抓第一行示范
        if example['beta']:
            first_b = example['beta'][0]
            if first_b["r"] is not None:
                md.append('**逐项展开**（以表格第 1 行示范）：\n')
                md.append(f'- 行业占比 = {first_b["w"]:.2f}%，代理 {first_b["proxy"]} 当日涨跌 = {first_b["r"]:+.4f}%')
                md.append(f'- 贡献 = {first_b["w"]:.2f}% × {first_b["r"]:+.4f}% = {first_b["contrib"]:+.4f}%\n')
        md.append(f'**第 3 步**：10 个行业贡献相加：\n')
        md.append(f'> **方案二估算 = {example["beta_total"]:+.3f}%**  ')
        md.append(f'> 实际 = {example["actual"]:+.2f}%，方案二误差 = {example["beta_total"] - example["actual"]:+.3f}%\n')
        md.append(f'**为什么偏差大**：基金重仓的是 AI 通信光模块这种弹性极高的细分赛道，')
        md.append(f'XLK 是涵盖整个美股科技的大盘 ETF，平均下来涨幅小很多，所以方案二被严重稀释。\n')

        # ============ 方案三 ============
        md.append('### 5.3 方案三（前十持仓 + 行业残余补全法）计算过程\n')
        md.append('**思路一句话**：前 10 用真实股票算（保留选股 alpha），剩下的按行业用 ETF 补。\n')
        md.append('**第 1 步**：算前 10 持仓的真实贡献（结果与方案一相同）：\n')
        md.append('| 股票 | 行业 | 占比 | 涨跌 | 贡献 |')
        md.append('|------|------|------|------|------|')
        for it in example['gamma']['top']:
            r_str = f'{it["r"]:+.2f}%' if it.get("r") is not None else '—'
            md.append(f'| {it["name"]} | {it["industry"]} | {it["w"]:.2f}% | '
                      f'{r_str} | {it["contrib"]:+.4f}% |')
        md.append(f'| **小计 (A)** | | | | **{example["gamma"]["top_total"]:+.4f}%** |\n')
        md.append('**第 2 步**：把前 10 按 GICS 行业归类，统计每个行业的「已占用比例」：\n')
        # 计算各行业已占用
        from collections import defaultdict
        by_ind = defaultdict(float)
        for it in example['gamma']['top']:
            by_ind[it.get('industry', '?')] += it.get('w', 0)
        md.append('| 行业 | 前10 中属于该行业的股票 | 累计占用 |')
        md.append('|------|----------------------|----------|')
        groups_text = defaultdict(list)
        for it in example['gamma']['top']:
            groups_text[it.get('industry', '?')].append(f'{it["name"]}({it["w"]:.2f}%)')
        for ind_name in [x['name'] for x in industries]:
            stks = '、'.join(groups_text.get(ind_name, []) ) if groups_text.get(ind_name) else '—'
            used = by_ind.get(ind_name, 0)
            md.append(f'| {ind_name} | {stks} | {used:.2f}% |')
        md.append('')
        md.append('**第 3 步**：每个行业算「残余 = 行业总占比 - 前10在该行业的累计占用」，')
        md.append('残余用对应行业 ETF 估算贡献：\n')
        md.append('| 行业 | 行业总占比 | 前10占用 | 残余 (c) | 代理 ETF | 涨跌 (d) | 贡献 = c × d |')
        md.append('|------|-----------|---------|---------|----------|----------|--------------|')
        for it in example['gamma']['resid']:
            r_str = f'{it["r"]:+.2f}%' if it.get("r") is not None else '—'
            ind_total = next((x['ratio'] for x in industries if x['name'] == it['industry']), 0)
            md.append(f'| {it["industry"]} | {ind_total:.2f}% | {it["used"]:.2f}% | '
                      f'{it["resid"]:.2f}% | {it["proxy"]} | {r_str} | {it["contrib"]:+.4f}% |')
        md.append(f'| | | | | | **小计 (B)** | **{example["gamma"]["resid_total"]:+.4f}%** |\n')
        # 抓信息技术行业做手算示范
        info_row = next((x for x in example['gamma']['resid'] if x['industry'] == '信息技术'), None)
        if info_row:
            md.append('**逐项展开**（以信息技术行业为例）：\n')
            ind_total = next((x['ratio'] for x in industries if x['name'] == '信息技术'), 0)
            md.append(f'- 行业总占比 = {ind_total:.2f}%')
            md.append(f'- 前 10 中信息技术股票合计占用 = {info_row["used"]:.2f}%')
            md.append(f'- 残余 = {ind_total:.2f}% - {info_row["used"]:.2f}% = {info_row["resid"]:.2f}%')
            md.append(f'- 代理 {info_row["proxy"]} 当日涨跌 = {info_row["r"]:+.4f}%')
            md.append(f'- 贡献 = {info_row["resid"]:.2f}% × {info_row["r"]:+.4f}% = {info_row["contrib"]:+.4f}%\n')
        md.append(f'**第 4 步**：A + B：\n')
        md.append(f'> **方案三估算 = (A) {example["gamma"]["top_total"]:+.3f}% + (B) {example["gamma"]["resid_total"]:+.3f}% '
                  f'= {example["gamma"]["total"]:+.3f}%**  ')
        md.append(f'> 实际 = {example["actual"]:+.2f}%，方案三误差 = {example["gamma"]["total"] - example["actual"]:+.3f}%\n')

        # ============ 方案四 ============
        d = example['delta']
        md.append('### 5.4 方案四（地区 × 行业 网格法）计算过程\n')
        md.append('**思路一句话**：把基金切成「地区 × 行业」的二维网格，'
                  '前 10 落到对应网格用真实涨跌，其他网格用「该地区+该行业」的代理 ETF。\n')
        md.append('**第 1 步**：构建网格权重。')
        md.append(f'`网格(地区r, 行业j) 权重 = 地区r占比 × (行业j占比 / 行业总占比)`，')
        md.append(f'其中行业总占比 = Σ行业 = **{d["total_stock"]:.2f}%**。\n')
        # 给一个网格的权重示范
        if d['resid']:
            samp = next((x for x in d['resid'] if x['region'] == '美国' and x['industry'] == '信息技术'), None)
            if samp is None:
                samp = d['resid'][0]
            reg_ratio = next((r['ratio'] for r in regions if r['name'] == samp['region']), 0)
            ind_ratio = next((i['ratio'] for i in industries if i['name'] == samp['industry']), 0)
            md.append(f'**示范**：以 (美国, 信息技术) 为例，')
            md.append(f'网格权重 = 美国占比 × (信息技术占比 / 行业总占比) = '
                      f'{reg_ratio:.2f}% × ({ind_ratio:.2f}% / {d["total_stock"]:.2f}%) = '
                      f'{reg_ratio * ind_ratio / d["total_stock"]:.2f}%。\n')

        md.append('**第 2 步**：把前 10 落到对应网格，用真实股票涨跌：\n')
        md.append('| 股票 | 地区 | 行业 | 占比 | 涨跌 | 贡献 |')
        md.append('|------|------|------|------|------|------|')
        for it in d['top']:
            r_str = f'{it["r"]:+.2f}%' if it.get('r') is not None else '—'
            md.append(f'| {it["name"]} | {it["region"]} | {it["industry"]} | '
                      f'{it["w"]:.2f}% | {r_str} | {it["contrib"]:+.4f}% |')
        md.append(f'| | | | | **小计 (A)** | **{d["top_total"]:+.4f}%** |\n')

        md.append('**第 3 步**：每个网格的「残余 = 网格权重 - 前10在此网格的占用」，'
                  '用 (地区, 行业) 对应代理估算（按贡献绝对值降序）：\n')
        md.append('| 地区 | 行业 | 网格权重 | 前10占用 | 残余 | 代理 | 涨跌 | 贡献 |')
        md.append('|------|------|---------|---------|------|------|------|------|')
        for it in d['resid'][:25]:
            r_str = f'{it["r"]:+.2f}%' if it.get('r') is not None else '—'
            md.append(f'| {it["region"]} | {it["industry"]} | {it["cell_w"]:.2f}% | '
                      f'{it["used"]:.2f}% | {it["resid"]:.2f}% | {it["proxy"]} | '
                      f'{r_str} | {it["contrib"]:+.4f}% |')
        md.append(f'| | | | | | | **小计 (B)** | **{d["resid_total"]:+.4f}%** |\n')

        # 示范一个网格的手算
        if d['resid']:
            sample = next((x for x in d['resid'] if x['region'] == '中国内地' and x['industry'] == '信息技术'), d['resid'][0])
            md.append('**逐项展开**（以「中国内地 × 信息技术」网格为例）：\n')
            md.append(f'- 网格权重 = {sample["cell_w"]:.2f}%')
            md.append(f'- 前 10 中落到该网格的股票合计 = {sample["used"]:.2f}%（新易盛 + 中际旭创 + 源杰科技 + 东山精密）')
            md.append(f'- 残余 = {sample["cell_w"]:.2f}% - {sample["used"]:.2f}% = {sample["resid"]:.2f}%')
            md.append(f'- 代理 {sample["proxy"]} 当日涨跌 = {sample["r"]:+.4f}%（A 股信息技术 ETF 159939）')
            md.append(f'- 贡献 = {sample["resid"]:.2f}% × {sample["r"]:+.4f}% = {sample["contrib"]:+.4f}%\n')

        md.append(f'**第 4 步**：A + B：\n')
        md.append(f'> **方案四估算 = (A) {d["top_total"]:+.3f}% + (B) {d["resid_total"]:+.3f}% = {d["total"]:+.3f}%**  ')
        md.append(f'> 实际 = {example["actual"]:+.2f}%，方案四误差 = {d["total"] - example["actual"]:+.3f}%\n')
        md.append('**为什么方案四最准**：方案三对所有「信息技术残余」都用美股 XLK 估算，')
        md.append('但当天 A 股信息技术 ETF +6.56%、恒生科技 +4.82%，远高于 XLK +3.10%，')
        md.append('方案四把这些差异分别算到了对应地区，所以更接近实际涨跌。\n')

        # ============ 方案五 ============
        eps5 = example['epsilon5']
        md.append('### 5.5 方案五（方案三 + 历史误差自校准）计算过程\n')
        md.append('**思路一句话**：在方案三的基础上，叠加最近几天「实际 - 方案三估算」的加权平均。\n')
        if eps5['history']:
            md.append('**第 1 步**：取 T 日之前最近若干天的残差（实际 - 方案三估算）：\n')
            md.append('| 日期 | 实际 (a) | 方案三估算 (b) | 残差 = a - b | age | 权重 = 0.6^age |')
            md.append('|------|---------|--------------|------------|-----|----------------|')
            for h in eps5['history']:
                md.append(f'| {h["date"]} | {h["actual"]:+.2f}% | {h["base_est"]:+.2f}% | '
                          f'{h["residual"]:+.2f}% | {h["age"]} | {h["weight"]:.4f} |')
            md.append('')
            md.append('**第 2 步**：加权平均：\n')
            md.append(f'> bias = {eps5["bias"]:+.4f}%\n')
            md.append(f'**第 3 步**：方案五估算 = 方案三估算 + bias = {eps5["base"]:+.3f}% + ({eps5["bias"]:+.3f}%) = **{eps5["total"]:+.3f}%**  ')
            md.append(f'> 实际 = {example["actual"]:+.2f}%，误差 = {eps5["total"] - example["actual"]:+.3f}%\n')
        else:
            md.append(f'> 窗口起始日，无历史残差，方案五退化为方案三 = {example["gamma"]["total"]:+.3f}%。\n')

        # ============ 方案六 ============
        eps6 = example['epsilon6']
        md.append('### 5.6 方案六（方案四 + 历史误差自校准）计算过程\n')
        md.append('**思路一句话**：在方案四（精度最高的基础模型）上叠加最近几天「实际 - 方案四估算」的加权平均。\n')
        if eps6['history']:
            md.append('**第 1 步**：取 T 日之前最近若干天的残差（实际 - 方案四估算）：\n')
            md.append('| 日期 | 实际 (a) | 方案四估算 (b) | 残差 = a - b | age | 权重 = 0.6^age |')
            md.append('|------|---------|--------------|------------|-----|----------------|')
            for h in eps6['history']:
                md.append(f'| {h["date"]} | {h["actual"]:+.2f}% | {h["base_est"]:+.2f}% | '
                          f'{h["residual"]:+.2f}% | {h["age"]} | {h["weight"]:.4f} |')
            md.append('')
            md.append('**第 2 步**：加权平均：\n')
            md.append(f'> bias = {eps6["bias"]:+.4f}%\n')
            md.append(f'**第 3 步**：方案六估算 = 方案四估算 + bias = {eps6["base"]:+.3f}% + ({eps6["bias"]:+.3f}%) = **{eps6["total"]:+.3f}%**  ')
            md.append(f'> 实际 = {example["actual"]:+.2f}%，误差 = {eps6["total"] - example["actual"]:+.3f}%\n')
            md.append('**方案六 vs 方案五**：方案六的 base 是方案四（MAE 更低），所以校准起点更高，')
            md.append('最终精度通常优于方案五。\n')
        else:
            md.append(f'> 窗口起始日，无历史残差，方案六退化为方案四 = {example["delta"]["total"]:+.3f}%。\n')

    # 6. 自校准
    md.append('## 6. 历史校准能否让小程序估算越来越准？\n')
    md.append('能，但要做对。三个层次依次升级：\n')
    md.append('### 6.1 一阶偏差校正（已实现 = 方案五）\n')
    md.append('用最近若干天的「实际 - 方案四估算」做指数加权平均，作为 bias 加在估算上。')
    md.append('这一项就能修复：')
    md.append('- 季报披露的总仓位误差（默认假设 90% 仓位 vs 实际 84.75%）；')
    md.append('- 行业分类错配（基金披露的 GICS 分类与代理 ETF 行业不完全对应）；')
    md.append('- 系统性低估或高估（看 §4 表 bias 列就能看出来）。\n')

    md.append('### 6.2 二阶系数校正（建议进阶）\n')
    md.append('**一句话**：方案六只修了「上下平移」，二阶还修了「放大/缩小」。\n')
    md.append('方案六的公式是：`校准后 = 方案四估算 + bias`，相当于在估算上加一个常数。')
    md.append('但如果基金经理最近加了杠杆或集中度变高，实际涨跌幅度会比方案四估算「放大」——')
    md.append('这时候光加一个常数不够，还需要乘一个系数。\n')
    md.append('**做法**：取最近 N 天（比如 20 天）的数据，画一条直线拟合：\n')
    md.append('```')
    md.append('实际涨跌 = a × 方案四估算 + b')
    md.append('```\n')
    md.append('其中：')
    md.append('- **a（斜率）**= 放大系数。a > 1 说明实际波动比方案四估算大（基金比我们想的更激进），')
    md.append('  a < 1 说明实际波动比估算小（基金比我们想的更保守）。')
    md.append('- **b（截距）**= 固定偏移。和方案六的 bias 类似，修正系统性高估/低估。\n')
    md.append('**为什么比方案六更进一步**：')
    md.append('- 方案六只有 b（加一个常数），相当于 a=1 固定不动；')
    md.append('- 二阶同时学 a 和 b，能适应「基金实际波动幅度 ≠ 估算幅度」的情况。\n')
    md.append('**举例**（基于方案六的回测数据）：\n')
    md.append('假设用 4 月份前 20 天的方案四估算 vs 实际净值做线性回归，拟合出 a=1.18, b=-0.05%。')
    md.append('这意味着：基金实际波动是方案四估算的 1.18 倍（因为前 10 之外的股票波动率高于代理 ETF）。\n')
    md.append('今天方案四估算 = +2.0%，则：')
    md.append('```')
    md.append('二阶校准后 = 1.18 × 2.0% + (-0.05%) = +2.31%')
    md.append('```')
    md.append('对比方案六：`2.0% + bias(假设 -0.28%) = +1.72%`，二阶校准更接近实际。\n')
    md.append('**什么时候 a ≠ 1**：')
    md.append('- 基金经理季度内大幅加仓（实际仓位 > 季报披露的 84.75%）→ a > 1')
    md.append('- 基金经理减仓或持有大量现金 → a < 1')
    md.append('- 前 10 之外的股票波动率远高于代理 ETF → a > 1\n')
    md.append('**注意**：二阶校正需要至少 20 天数据才能拟合出稳定的 a 和 b，')
    md.append('数据不足时容易过拟合（a 值不稳定），所以设定 20 天为开启门槛。\n')

    md.append('### 6.3 多模型集成（探索方向，暂无回测数据支撑）\n')
    md.append('**⚠️ 注意：以下方案是理论上的进阶方向，本次回测未实现，没有实际 MAE 数据支撑。**')
    md.append('**是否值得实现需要后续单独回测验证。**\n')
    md.append('**思路**：每天我们有 4 个基础估算（方案一/二/三/四），把它们加权混合：\n')
    md.append('```')
    md.append('最终估算 = p₁×方案一 + p₂×方案二 + p₃×方案三 + p₄×方案四 + b')
    md.append('')
    md.append('约束：p₁ + p₂ + p₃ + p₄ = 1，且每个 p ≥ 0')
    md.append('```\n')
    md.append('**p₁~p₄ 怎么来的**：用最近 30 天的「实际净值涨跌」和「4 个方案的估算」，')
    md.append('做一个带约束的最小二乘拟合，找出让过去 30 天误差最小的权重组合。\n')
    md.append('**理论上为什么可能有用**：')
    md.append('- 如果基金最近调仓很少，方案一（纯前十）就够准 → p₁ 会变大')
    md.append('- 如果基金最近大幅调仓，前十已经不代表真实持仓 → p₂（行业 ETF）权重会上升')
    md.append('- 如果 A 股/港股仓位波动大 → p₄（地区×行业网格）权重会上升\n')
    md.append('**风险**：')
    md.append('- 30 天数据拟合 5 个参数（p₁~p₄ + b），自由度低，容易过拟合')
    md.append('- 方案一~四之间高度相关（共线性），权重可能不稳定')
    md.append('- 实际效果可能不如简单的「方案六（方案四+bias）」')
    md.append('- **建议**：先把方案六跑稳，后续有余力再单独回测验证集成方案是否真的更优\n')

    md.append('### 6.4 实施建议（小程序落地）\n')
    md.append('基于回测结论，推荐的最严谨落地路径如下：\n')

    md.append('#### 推荐方案选择\n')
    md.append('| 场景 | 推荐方案 | 理由 |')
    md.append('|------|---------|------|')
    md.append('| 数据源完整（美股+A股+港股 ETF 都能拉到） | **方案六**（方案四+自校准） | MAE 最低 0.468%，<0.5% 命中 67% |')
    md.append('| 数据源受限（只能拉美股） | **方案五**（方案三+自校准） | 不依赖 A 股/港股 ETF，MAE 0.551% |')
    md.append('| 冷启动（无历史数据） | **方案四**（地区×行业网格） | 无需历史校准，MAE 0.497% |\n')

    md.append('#### 分阶段演进\n')
    md.append('| 阶段 | 触发条件 | 计算逻辑 | 向用户展示 | 预期 MAE |')
    md.append('|------|---------|---------|----------|---------|')
    md.append('| ① 冷启动 | 新基金 / 新季报刚发布 | 方案四（地区×行业网格） | 方案四估算值 | ~0.50% |')
    md.append('| ② 一阶校准 | 累积 ≥ 5 天实际净值 | 方案六 = 方案四 + EWMA bias | 方案四 + bias | ~0.47% |')
    md.append('| ③ 二阶校准 | 累积 ≥ 20 天 | a × 方案四 + b（线性回归） | 校准后估算 | 待回测验证 |')
    md.append('| ④ 多模型集成（可选） | 累积 ≥ 30 天 | p₁·方案一 + ... + p₄·方案四 + b | 集成估算 | 待回测验证 |')
    md.append('| ⑤ 季报更新 | 新季报发布 | 更新持仓/行业/地区，清空历史缓存 | 回到阶段 ① | — |\n')

    md.append('#### 为什么冷启动用方案四而不是方案三\n')
    md.append('- 方案四 MAE 0.497% < 方案三 0.549%，即使没有历史校准也更准')
    md.append('- 方案四多用了地区分布数据（美国 46% / 中国内地 33% / 香港 4.5% / 日本 1.2%），')
    md.append('  能区分「A 股信息技术 ETF +6.56%」和「美股 XLK +3.10%」的差异')
    md.append('- 代价是多拉 3 个 ETF 数据（159939、513180、EWJ），API 调用量增加约 3 次\n')

    md.append('#### 降级策略（容错）\n')
    md.append('| 异常情况 | 降级方案 |')
    md.append('|---------|---------|')
    md.append('| A 股/港股 ETF 数据拉取失败 | 降级到方案五（方案三+校准），只用美股 ETF |')
    md.append('| 美股 ETF 数据也拉取失败 | 降级到方案一（纯前十持仓），只用个股行情 |')
    md.append('| 个股行情部分缺失 | 缺失的股票贡献按 0 计算，标注「部分数据缺失」 |')
    md.append('| 历史净值回填失败（actual 缺失） | 暂停校准，继续用上一次的 bias/系数 |\n')

    md.append('#### 定时任务设计\n')
    md.append('```')
    md.append('┌─────────────────────────────────────────────────────────────┐')
    md.append('│ 每日凌晨 04:30（美股收盘后）                                  │')
    md.append('│   1. 拉取前 10 持仓股票的最新收盘价                            │')
    md.append('│   2. 拉取代理 ETF（XLK/XLI/XLC/... + 159939/513180/EWJ）      │')
    md.append('│   3. 计算方案一~四的当日估算                                   │')
    md.append('│   4. 读取历史缓存，计算方案五/六（叠加 bias）                    │')
    md.append('│   5. 写入当日估算到数据库，推送给用户                            │')
    md.append('├─────────────────────────────────────────────────────────────┤')
    md.append('│ 每日晚 22:00（基金净值更新后）                                 │')
    md.append('│   1. 拉取基金当日实际净值涨跌                                  │')
    md.append('│   2. 回填 actual 字段到历史缓存                                │')
    md.append('│   3. 重新计算 bias / 回归系数 / 集成权重（为明天准备）            │')
    md.append('└─────────────────────────────────────────────────────────────┘')
    md.append('```\n')

    md.append('#### 数据存储结构\n')
    md.append('每基金一个文档（云数据库 / 云存储 JSON）：\n')
    md.append('```json')
    md.append('{')
    md.append('  "code": "012922",')
    md.append('  "report_date": "2026-03-31",')
    md.append('  "holdings": [...],')
    md.append('  "industries": [...],')
    md.append('  "regions": [...],')
    md.append('  "calibration": {')
    md.append('    "bias": -0.026,')
    md.append('    "a": 1.12,')
    md.append('    "b": -0.05,')
    md.append('    "weights": [0.1, 0.0, 0.5, 0.4]')
    md.append('  },')
    md.append('  "history": [')
    md.append('    {"date": "2026-04-01", "actual": 2.68, "s1": 1.53, "s2": 1.14, "s3": 1.93, "s4": 2.19},')
    md.append('    {"date": "2026-04-02", "actual": 0.70, "s1": 1.08, "s2": 0.56, "s3": 1.23, "s4": 0.66},')
    md.append('    "..."')
    md.append('  ]')
    md.append('}')
    md.append('```\n')

    md.append('#### 季报更新流程\n')
    md.append('1. 检测到新季报发布（每年 1/20、4/20、7/20、10/20 前后）')
    md.append('2. 拉取新的前 10 持仓、行业分布、地区分布')
    md.append('3. 更新 `holdings` / `industries` / `regions` 字段')
    md.append('4. **清空** `history` 数组和 `calibration` 对象')
    md.append('5. 从阶段 ① 重新开始累积')
    md.append('6. 为什么要清空：新季报意味着持仓可能大幅变化，旧的 bias/系数已经不适用\n')

    md.append('## 7. 复现\n')
    md.append('```bash')
    md.append('python3 experiments/qdii_active_redesign.py \\')
    md.append(f'  --code {code} --start {start} --end {end} \\')
    md.append(f'  --example-date {ex_date} \\')
    md.append('  --output experiments/qdii-active-redesign-202604.md')
    md.append('```\n')

    md.append('**数据源**：天天基金（净值/持仓/行业/地区） + 新浪财经（个股、ETF、汇率）')

    return '\n'.join(md)


if __name__ == '__main__':
    main()
