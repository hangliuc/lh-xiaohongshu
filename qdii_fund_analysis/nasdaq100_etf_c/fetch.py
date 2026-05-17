# -*- coding: utf-8 -*-
import json
import os
import random
import re
import time
from datetime import datetime
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "http://fund.eastmoney.com/",
}

NASDAQ100_CODES = [
    "006479", "008971", "008008", "008345", "008346",
    "012888", "016503", "017062", "017245", "017008", "017106", "017345"
]

def fetch_fund(code):
    result = {"code": code}
    try:
        html = requests.get(f"http://fund.eastmoney.com/{code}.html", headers=HEADERS, timeout=30).text
        html = html.encode('utf-8').decode('utf-8', errors='ignore')
        
        name_match = re.search(r"<title>(.*?)\((\d{6})\)", html)
        if name_match:
            result["name"] = name_match.group(1).strip()
        
        scale_match = re.search(r"规模\s*[：:]\s*([\d.]+)(亿元|万)", html)
        if scale_match:
            result["scale"] = scale_match.group(1) + scale_match.group(2)
        
        for label in ["近1年", "近一年"]:
            match = re.search(re.escape(label) + r"[：:]\s*</span>\s*<span[^>]*>([-\d.]+)%?</span>", html)
            if match:
                result["return_1y"] = match.group(1) + "%"
                break
        
        if "暂停" in html:
            result["limit"] = "暂停申购"
        else:
            result["limit"] = "无限制"
            
        fees_html = requests.get(f"http://fundf10.eastmoney.com/jjfl_{code}.html", headers=HEADERS, timeout=30).text
        mgmt_match = re.search(r"管理费率[^\d]*<td[^>]*>([\d.]+)%?", fees_html)
        result["fee_management"] = mgmt_match.group(1) + "%" if mgmt_match else "0.80%"
        cust_match = re.search(r"托管费率[^\d]*<td[^>]*>([\d.]+)%?", fees_html)
        result["fee_custodian"] = cust_match.group(1) + "%" if cust_match else "0.20%"
        svc_match = re.search(r"销售服务费率[^\d]*<td[^>]*>([\d.]+)%?", fees_html)
        result["fee_service"] = svc_match.group(1) + "%" if svc_match else "0.30%"
        
        total = float(result["fee_management"].replace("%", "")) + float(result["fee_custodian"].replace("%", "")) + float(result["fee_service"].replace("%", ""))
        result["fee_total"] = f"{total:.2f}%"
        
    except Exception as e:
        print(f"Error fetching {code}: {e}")
    
    return result

def main():
    funds = []
    for code in NASDAQ100_CODES:
        fund = fetch_fund(code)
        if "name" in fund:
            funds.append(fund)
        time.sleep(random.uniform(0.5, 1.0))
    
    result = {
        "title": "被动型纳斯达克100 ETF (C类) 硬核对比",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "funds": funds
    }
    
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"Fetched {len(funds)} funds")

if __name__ == "__main__":
    main()
