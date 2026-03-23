#!/usr/bin/env python3
"""
CPU Mining Coin Scanner - 每日自动扫描 CPU 可挖新币

数据源: WhatToMine CPU API (https://whattomine.com/cpu.json)

功能:
  - 每日扫描所有 CPU 可挖币种
  - 对比昨日数据，发现新上线币种
  - 按 BTC 收益排名
  - 输出 JSON + 文本报告
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

WHATTOMINE_CPU_URL = "https://whattomine.com/cpu.json"
BTC_PRICE_USD = 87000  # 粗略估价，可后续接 API


def fetch_json(url, retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"  Attempt {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    return None


def fetch_cpu_coins():
    """从 WhatToMine 获取所有 CPU 可挖币."""
    print("[*] Fetching WhatToMine CPU coins...")
    data = fetch_json(WHATTOMINE_CPU_URL)
    if not data or "coins" not in data:
        print("  [!] Fetch failed")
        return []

    coins = []
    for name, info in data["coins"].items():
        if name.startswith("Nicehash"):
            continue  # 跳过 Nicehash 条目

        btc_rev = float(info.get("btc_revenue", 0))
        coins.append({
            "name": name,
            "symbol": info.get("tag", ""),
            "algorithm": info.get("algorithm", ""),
            "block_time": info.get("block_time", ""),
            "block_reward": info.get("block_reward", 0),
            "nethash": info.get("nethash", 0),
            "difficulty": info.get("difficulty", 0),
            "exchange_rate_btc": info.get("exchange_rate", 0),
            "market_cap": info.get("market_cap", "$0"),
            "estimated_rewards_24h": info.get("estimated_rewards", "0"),
            "btc_revenue_24h": info.get("btc_revenue", "0"),
            "btc_revenue_24h_float": btc_rev,
            "usd_revenue_24h": round(btc_rev * BTC_PRICE_USD, 4),
            "profitability": info.get("profitability", 0),
            "profitability24": info.get("profitability24", 0),
            "volume_btc": info.get("exchange_rate_vol", 0),
            "lagging": info.get("lagging", False),
            "source": "whattomine",
            "id": info.get("id", 0),
        })

    coins.sort(key=lambda c: c["btc_revenue_24h_float"], reverse=True)
    print(f"  Found {len(coins)} CPU-mineable coins")
    return coins


def load_previous_day():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    path = DATA_DIR / f"{yesterday}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    # 也试试更早的日期
    for days_back in range(2, 8):
        d = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        path = DATA_DIR / f"{d}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return None


def find_new_coins(today_coins, prev_data):
    if not prev_data:
        return []  # 首次运行无法对比
    old_symbols = {c["symbol"] for c in prev_data.get("coins", [])}
    return [c for c in today_coins if c["symbol"] not in old_symbols]


def find_disappeared(today_coins, prev_data):
    if not prev_data:
        return []
    new_symbols = {c["symbol"] for c in today_coins}
    return [c for c in prev_data.get("coins", []) if c["symbol"] not in new_symbols]


def generate_report(coins, new_coins, disappeared, date_str, prev_date):
    return {
        "date": date_str,
        "compared_to": prev_date,
        "scan_time": datetime.now().isoformat(),
        "total_cpu_coins": len(coins),
        "new_coins_count": len(new_coins),
        "disappeared_count": len(disappeared),
        "coins": coins,
        "new_coin_alerts": new_coins,
        "disappeared_coins": disappeared,
    }


def format_report_text(report):
    lines = []
    lines.append(f"⛏️ CPU 挖矿扫描报告 - {report['date']}")
    lines.append(f"扫描时间: {report['scan_time']}")
    lines.append(f"CPU 可挖币种: {report['total_cpu_coins']} 个")
    if report["compared_to"]:
        lines.append(f"对比日期: {report['compared_to']}")
    lines.append("")

    # 新币告警
    if report["new_coin_alerts"]:
        lines.append("🆕 ===== 新发现币种 =====")
        for c in report["new_coin_alerts"]:
            lines.append(f"  🔥 {c['name']} ({c['symbol']})")
            lines.append(f"     算法: {c['algorithm']} | 市值: {c['market_cap']}")
            lines.append(f"     日收益: {c['btc_revenue_24h']} BTC (≈${c['usd_revenue_24h']})")
            lines.append(f"     收益率: {c['profitability']}%")
        lines.append("")

    # 消失的币
    if report.get("disappeared_coins"):
        lines.append("❌ 消失的币种:")
        for c in report["disappeared_coins"]:
            lines.append(f"  • {c['name']} ({c['symbol']})")
        lines.append("")

    # 收益排行
    lines.append("📈 收益排行 (基于 1kH/s RandomX):")
    for i, c in enumerate(report["coins"], 1):
        flag = "🟢" if c["profitability"] >= 100 else "🔴"
        lag = " ⚠️滞后" if c.get("lagging") else ""
        lines.append(f"  {flag} {i}. {c['name']} ({c['symbol']}) - {c['algorithm']}")
        lines.append(f"     日收益: {c['btc_revenue_24h']} BTC (≈${c['usd_revenue_24h']}) | 收益率: {c['profitability']}% | 市值: {c['market_cap']}{lag}")

    return "\n".join(lines)


def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"=== CPU Mining Scanner - {date_str} ===\n")

    # 1. 获取今日数据
    coins = fetch_cpu_coins()
    if not coins:
        print("[!] No coins fetched, exiting.")
        sys.exit(1)

    # 2. 对比历史
    prev_data = load_previous_day()
    prev_date = prev_data["date"] if prev_data else None
    new_coins = find_new_coins(coins, prev_data)
    disappeared = find_disappeared(coins, prev_data)

    # 3. 生成报告
    report = generate_report(coins, new_coins, disappeared, date_str, prev_date)

    # 4. 保存 JSON
    output_path = DATA_DIR / f"{date_str}.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[+] JSON saved: {output_path}")

    # 5. 输出文本报告
    text_report = format_report_text(report)
    print(f"\n{text_report}")

    # 6. 保存文本报告
    text_path = DATA_DIR / f"{date_str}.txt"
    with open(text_path, "w") as f:
        f.write(text_report)
    print(f"\n[+] Text saved: {text_path}")

    # 返回新币数量（供 cron 判断是否需要告警）
    if new_coins:
        print(f"\n🚨 发现 {len(new_coins)} 个新币！")
    return report


if __name__ == "__main__":
    main()
