#!/usr/bin/env python3
"""
CPU 新币猎手 - 多源自动发现 CPU 可挖新币

数据源:
  1. BitcoinTalk ANN 板 (Altcoins Announcements) - 最权威的新币公告
  2. GitHub 新仓库 - 刚发布代码的 CPU 挖矿项目
  3. WhatToMine CPU - 已上线的 CPU 币收益排行

功能:
  - 每日扫描所有源，发现新项目
  - 对比历史数据，标记首次出现的项目
  - 按来源和时间排序
  - 输出报告 + 告警
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from html.parser import HTMLParser

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

KNOWN_DB = DATA_DIR / "known_projects.json"

# X/Twitter 搜索关键词
X_SEARCH_QUERIES = [
    "cpu mining new coin",
    "cpu mineable fair launch",
    "randomx new coin launch",
    "yespower new coin",
    "cpu mining cryptocurrency launch",
    "cpu pow coin launch",
]

# CPU 相关关键词
CPU_KEYWORDS = [
    "cpu", "randomx", "cryptonight", "yespower", "yescrypt",
    "ghostrider", "cpupower", "argon2", "minotaurx", "equihash",
    "sha256mem", "astrobwt", "verushash", "panthera",
]

MINING_KEYWORDS = [
    "mine", "miner", "mining", "pow", "proof-of-work",
    "hashrate", "block reward", "halving", "mineable",
]


def fetch_url(url, headers=None, retries=2, timeout=30):
    """通用 URL 抓取."""
    default_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    }
    if headers:
        default_headers.update(headers)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=default_headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"    Fetch attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None


def fetch_json(url, headers=None):
    text = fetch_url(url, headers)
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


# ========== SOURCE 0: X/Twitter ==========

def scan_x_twitter():
    """扫描 X/Twitter 上的 CPU 挖矿新币信息.
    
    通过 X Syndication API（无需登录）获取已知矿币账号和搜索结果。
    """
    print("[1/4] Scanning X/Twitter for CPU mining coins...")
    results = []
    seen = set()

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

    # 已知 CPU 矿币项目的 X 账号
    cpu_mining_accounts = [
        # 成熟项目
        "DeroProject", "getmonero", "Raptoreum", "EpicCashTech",
        "ZephyrProtocol", "VerusCoin", "taboroietwork", "ZanoProject",
        # 新项目（从 BitcoinTalk 发现的）
        "FairchainDev", "fairchain_io", "BotchainCoin", "botchain_io",
        "DilithionCoin", "BasecoinDev", "BitMoneroCoin",
        "TaronNetwork", "ObiDogeCoin", "SmartieCoin",
        "c64chain", "CatCoinDev", "WaecnanChain", "LuckyPepeCoin",
        # 挖矿信息聚合
        "cpumininginfo", "MiningPoolStats", "WhatToMine",
    ]

    for account in cpu_mining_accounts:
        try:
            url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{account}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                page = resp.read().decode("utf-8", errors="replace")

            # 提取 JSON
            json_match = re.search(
                r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, re.DOTALL
            )
            if not json_match:
                continue

            import html as html_lib
            data = json.loads(json_match.group(1))
            timeline = data.get("props", {}).get("pageProps", {}).get("timeline", {})
            entries = timeline.get("entries", [])

            if not entries:
                continue

            # 只看最近的推文
            for entry in entries[:5]:
                content = entry.get("content", {})
                tweet = content.get("tweet", content)
                text = tweet.get("text", "")
                tweet_id = tweet.get("id_str", "")
                created = tweet.get("created_at", "")

                if not text:
                    continue

                # 检查是否与 CPU 挖矿/新币相关
                text_lower = text.lower()
                is_relevant = any(kw in text_lower for kw in [
                    "cpu", "mining", "mine", "miner", "launch", "mainnet",
                    "new coin", "fair launch", "randomx", "yespower",
                    "pow", "block reward", "halving", "hashrate",
                    "testnet", "node", "wallet", "pool",
                ])

                if is_relevant and tweet_id not in seen:
                    seen.add(tweet_id)
                    clean_text = html_lib.unescape(text)[:200]
                    results.append({
                        "source": "x_twitter",
                        "username": account,
                        "tweet_id": tweet_id,
                        "url": f"https://x.com/{account}/status/{tweet_id}" if tweet_id else f"https://x.com/{account}",
                        "text": clean_text,
                        "snippet": clean_text,
                        "title": f"@{account}",
                        "created_at": created,
                        "search_query": "syndication_api",
                    })

        except Exception:
            continue  # 静默跳过失败的账号

        time.sleep(0.5)  # 限速

    # 按时间排序（最新的在前）
    results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    print(f"    Found {len(results)} X/Twitter mentions")
    return results


# ========== SOURCE 1: BitcoinTalk ANN ==========

def scan_bitcointalk():
    """扫描 BitcoinTalk Altcoin Announcements 板块，查找 CPU 挖矿新币."""
    print("[1/3] Scanning BitcoinTalk ANN board...")
    results = []

    # 扫描前几页
    for page in range(3):  # 前3页，每页20个帖子
        offset = page * 40
        url = f"https://bitcointalk.org/index.php?board=159.{offset}"
        html = fetch_url(url)
        if not html:
            continue

        # 提取帖子标题和链接
        # 格式: <a href="...topic=XXXX.0">TITLE</a>
        topics = re.findall(
            r'<a\s+href="https://bitcointalk\.org/index\.php\?topic=(\d+)\.0"[^>]*>([^<]+)</a>',
            html
        )

        for topic_id, title in topics:
            title_lower = title.lower()
            # 检查是否与 CPU 挖矿相关
            is_cpu = any(kw in title_lower for kw in CPU_KEYWORDS)
            is_mining = any(kw in title_lower for kw in MINING_KEYWORDS)
            is_ann = "[ann]" in title_lower or "ann" in title_lower

            if is_cpu or (is_mining and is_ann):
                results.append({
                    "source": "bitcointalk",
                    "title": title.strip(),
                    "url": f"https://bitcointalk.org/index.php?topic={topic_id}.0",
                    "topic_id": topic_id,
                    "is_cpu_explicit": is_cpu,
                })

        time.sleep(1)  # 限速

    # 去重
    seen = set()
    unique = []
    for r in results:
        if r["topic_id"] not in seen:
            seen.add(r["topic_id"])
            unique.append(r)

    print(f"    Found {len(unique)} CPU mining-related threads")
    return unique


# ========== SOURCE 2: GitHub ==========

def scan_github():
    """搜索 GitHub 上新创建的 CPU 挖矿项目."""
    print("[2/3] Scanning GitHub for new CPU mining repos...")
    results = []

    queries = [
        "cpu+mining+coin+created:>{since}",
        "cpu+mineable+cryptocurrency+created:>{since}",
        "randomx+coin+created:>{since}",
        "pow+blockchain+cpu+created:>{since}",
        "yespower+coin+created:>{since}",
        "cpu+miner+blockchain+created:>{since}",
    ]

    since = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    seen_repos = set()

    for q_template in queries:
        q = q_template.format(since=since)
        url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page=20"
        data = fetch_json(url, headers={"Accept": "application/vnd.github.v3+json"})
        if not data or "items" not in data:
            continue

        for repo in data["items"]:
            full_name = repo["full_name"]
            if full_name in seen_repos:
                continue
            seen_repos.add(full_name)

            desc = (repo.get("description") or "").lower()
            name_lower = full_name.lower()
            topics = [t.lower() for t in repo.get("topics", [])]
            combined = f"{name_lower} {desc} {' '.join(topics)}"

            # 确认是 CPU 挖矿相关
            is_cpu = any(kw in combined for kw in CPU_KEYWORDS)
            is_mining = any(kw in combined for kw in MINING_KEYWORDS)

            if is_cpu or is_mining:
                # 安全检查：分析仓库内容
                risk_flags = []
                trust_score = 5  # 满分10

                # 没有源码语言 → 可能只有二进制
                if not repo.get("language"):
                    risk_flags.append("⚠️ 无源码语言(可能仅含二进制)")
                    trust_score -= 3

                # 0 星 0 fork → 全新无人验证
                if repo["stargazers_count"] == 0 and repo["forks_count"] == 0:
                    risk_flags.append("⚠️ 零星零fork(无人验证)")
                    trust_score -= 1

                # 检查是否有可疑文件（通过 API 查看仓库内容）
                contents_url = f"https://api.github.com/repos/{full_name}/contents"
                contents = fetch_json(contents_url, headers={"Accept": "application/vnd.github.v3+json"})
                has_source = False
                has_binary_only = False
                exe_count = 0
                source_count = 0
                if contents and isinstance(contents, list):
                    source_exts = {".py", ".go", ".rs", ".c", ".cpp", ".h", ".js", ".ts", ".sol", ".java", ".cs"}
                    binary_exts = {".exe", ".dll", ".bin", ".msi", ".dmg", ".app"}
                    for item in contents:
                        name_l = item.get("name", "").lower()
                        for ext in source_exts:
                            if name_l.endswith(ext):
                                source_count += 1
                                has_source = True
                        for ext in binary_exts:
                            if name_l.endswith(ext):
                                exe_count += 1
                        # 检查 src/ 或常见源码目录
                        if item.get("type") == "dir" and item.get("name", "").lower() in ["src", "lib", "cmd", "pkg", "internal"]:
                            has_source = True
                            source_count += 1

                    if exe_count > 0 and not has_source:
                        has_binary_only = True
                        risk_flags.append("🚨 仅含二进制文件(无源码!高风险)")
                        trust_score -= 4
                    elif exe_count > 0 and has_source:
                        risk_flags.append("⚠️ 含预编译二进制+源码")
                        trust_score -= 1

                # 账户太新也是风险
                # (通过 owner 信息判断)
                owner = repo.get("owner", {})
                if owner.get("type") == "User":
                    owner_url = f"https://api.github.com/users/{owner.get('login','')}"
                    owner_info = fetch_json(owner_url, headers={"Accept": "application/vnd.github.v3+json"})
                    if owner_info:
                        public_repos = owner_info.get("public_repos", 0)
                        followers = owner_info.get("followers", 0)
                        if public_repos <= 1 and followers == 0:
                            risk_flags.append("⚠️ 新账户(仅1个仓库,0粉丝)")
                            trust_score -= 1

                trust_score = max(0, min(10, trust_score))

                results.append({
                    "source": "github",
                    "name": repo["full_name"],
                    "url": repo["html_url"],
                    "description": repo.get("description", ""),
                    "stars": repo["stargazers_count"],
                    "forks": repo["forks_count"],
                    "created_at": repo["created_at"],
                    "updated_at": repo["updated_at"],
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                    "risk_flags": risk_flags,
                    "trust_score": trust_score,
                    "has_binary_only": has_binary_only,
                    "exe_count": exe_count,
                    "source_count": source_count,
                })

        time.sleep(1)  # GitHub rate limit

    print(f"    Found {len(results)} repos")
    return results


# ========== SOURCE 3: WhatToMine CPU ==========

def scan_whattomine():
    """从 WhatToMine 获取 CPU 可挖币排行."""
    print("[3/3] Scanning WhatToMine CPU coins...")
    data = fetch_json("https://whattomine.com/cpu.json")
    if not data or "coins" not in data:
        print("    WhatToMine fetch failed")
        return []

    coins = []
    for name, info in data["coins"].items():
        if name.startswith("Nicehash"):
            continue
        btc_rev = float(info.get("btc_revenue", 0))
        coins.append({
            "source": "whattomine",
            "name": name,
            "symbol": info.get("tag", ""),
            "algorithm": info.get("algorithm", ""),
            "market_cap": info.get("market_cap", "$0"),
            "btc_revenue_24h": info.get("btc_revenue", "0"),
            "btc_revenue_float": btc_rev,
            "profitability": info.get("profitability", 0),
            "lagging": info.get("lagging", False),
        })

    coins.sort(key=lambda c: c["btc_revenue_float"], reverse=True)
    print(f"    Found {len(coins)} CPU coins")
    return coins


# ========== 对比历史，发现新项目 ==========

def load_known_projects():
    if KNOWN_DB.exists():
        with open(KNOWN_DB) as f:
            return json.load(f)
    return {"bitcointalk_topics": [], "github_repos": [], "whattomine_symbols": [], "x_tweet_ids": [], "last_updated": ""}


def save_known_projects(known):
    known["last_updated"] = datetime.now().isoformat()
    with open(KNOWN_DB, "w") as f:
        json.dump(known, f, indent=2, ensure_ascii=False)


def find_new_projects(x_results, btt_results, gh_results, wtm_results, known):
    known_tweet_ids = set(known.get("x_tweet_ids", []))
    new_x = [r for r in x_results if r.get("tweet_id") and r["tweet_id"] not in known_tweet_ids]
    # 对于没有 tweet_id 的（账号级别），用 username 去重
    known_usernames = {r.get("username") for r in x_results if r.get("tweet_id") in known_tweet_ids}
    new_x += [r for r in x_results if not r.get("tweet_id") and r.get("username") not in known_usernames]
    new_btt = [r for r in btt_results if r["topic_id"] not in known["bitcointalk_topics"]]
    new_gh = [r for r in gh_results if r["name"] not in known["github_repos"]]
    new_wtm = [r for r in wtm_results if r["symbol"] not in known["whattomine_symbols"]]
    return new_x, new_btt, new_gh, new_wtm


def update_known(x_results, btt_results, gh_results, wtm_results, known):
    known["x_tweet_ids"] = list(set(
        known.get("x_tweet_ids", []) + [r["tweet_id"] for r in x_results if r.get("tweet_id")]
    ))
    known["bitcointalk_topics"] = list(set(
        known["bitcointalk_topics"] + [r["topic_id"] for r in btt_results]
    ))
    known["github_repos"] = list(set(
        known["github_repos"] + [r["name"] for r in gh_results]
    ))
    known["whattomine_symbols"] = list(set(
        known["whattomine_symbols"] + [r["symbol"] for r in wtm_results]
    ))
    return known


# ========== 报告 ==========

def format_report(date_str, new_x, new_btt, new_gh, new_wtm, all_x, all_btt, all_gh, all_wtm, is_first_run):
    lines = []
    lines.append(f"⛏️ CPU 新币猎手报告 - {date_str}")
    lines.append(f"扫描时间: {datetime.now().strftime('%H:%M:%S')}")
    lines.append(f"数据源: X/Twitter + BitcoinTalk ANN + GitHub + WhatToMine")
    lines.append("")

    if is_first_run:
        lines.append("📌 首次运行，以下为全量数据（后续只报新增）")
        lines.append("")

    # === 新发现 ===
    total_new = len(new_x) + len(new_btt) + len(new_gh) + len(new_wtm)
    if total_new > 0:
        lines.append(f"🆕 ===== 新发现项目: {total_new} 个 =====")
        lines.append("")

    if new_x:
        lines.append("🐦 X/Twitter 新动态:")
        for r in new_x:
            lines.append(f"  • @{r['username']}: {r['snippet'][:120]}")
            lines.append(f"    {r['url']}")
        lines.append("")

    if new_btt:
        lines.append("📋 BitcoinTalk 新公告:")
        for r in new_btt:
            cpu_tag = " 🔥CPU" if r["is_cpu_explicit"] else ""
            lines.append(f"  • {r['title']}{cpu_tag}")
            lines.append(f"    {r['url']}")
        lines.append("")

    if new_gh:
        lines.append("💻 GitHub 新项目:")
        for r in new_gh:
            trust = r.get('trust_score', '?')
            trust_icon = "🟢" if trust >= 7 else "🟡" if trust >= 4 else "🔴"
            binary_warn = " 🚨仅二进制!" if r.get('has_binary_only') else ""
            lines.append(f"  • {trust_icon} {r['name']} ⭐{r['stars']} ({r['language'] or 'N/A'}) [信任:{trust}/10]{binary_warn}")
            if r.get('description'):
                lines.append(f"    {r['description'][:100]}")
            lines.append(f"    创建: {r['created_at'][:10]} | {r['url']}")
            if r.get('risk_flags'):
                for flag in r['risk_flags']:
                    lines.append(f"    {flag}")
        lines.append("")

    if new_wtm:
        lines.append("📊 WhatToMine 新上线:")
        for r in new_wtm:
            lines.append(f"  • {r['name']} ({r['symbol']}) - {r['algorithm']}")
            lines.append(f"    市值: {r['market_cap']} | 日收益: {r['btc_revenue_24h']} BTC | 收益率: {r['profitability']}%")
        lines.append("")

    if total_new == 0 and not is_first_run:
        lines.append("✅ 今日无新发现")
        lines.append("")

    # === 汇总 ===
    lines.append("📊 ===== 汇总 =====")
    lines.append(f"X/Twitter 动态: {len(all_x)} 条")
    lines.append(f"BitcoinTalk CPU 相关帖子: {len(all_btt)} 个")
    lines.append(f"GitHub CPU 挖矿项目: {len(all_gh)} 个")
    lines.append(f"WhatToMine CPU 币种: {len(all_wtm)} 个")
    lines.append("")

    # WhatToMine Top 5
    if all_wtm:
        lines.append("📈 WhatToMine 收益 Top 5:")
        for i, c in enumerate(all_wtm[:5], 1):
            lines.append(f"  {i}. {c['name']} ({c['symbol']}) - {c['algorithm']} | {c['btc_revenue_24h']} BTC/天 | {c['profitability']}%")

    return "\n".join(lines)


def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"=== CPU 新币猎手 - {date_str} ===\n")

    # 加载历史
    known = load_known_projects()
    is_first_run = not known["last_updated"]

    # 扫描四个数据源
    x_results = scan_x_twitter()
    btt_results = scan_bitcointalk()
    gh_results = scan_github()
    wtm_results = scan_whattomine()

    # 发现新项目
    new_x, new_btt, new_gh, new_wtm = find_new_projects(x_results, btt_results, gh_results, wtm_results, known)

    # 更新已知库
    known = update_known(x_results, btt_results, gh_results, wtm_results, known)
    save_known_projects(known)

    # 生成报告
    report_text = format_report(date_str, new_x, new_btt, new_gh, new_wtm,
                                 x_results, btt_results, gh_results, wtm_results, is_first_run)
    print(f"\n{report_text}")

    # 保存
    report_data = {
        "date": date_str,
        "scan_time": datetime.now().isoformat(),
        "is_first_run": is_first_run,
        "new_x_twitter": new_x,
        "new_bitcointalk": new_btt,
        "new_github": new_gh,
        "new_whattomine": new_wtm,
        "all_x_twitter": x_results,
        "all_bitcointalk": btt_results,
        "all_github": gh_results,
        "all_whattomine": wtm_results,
    }
    json_path = DATA_DIR / f"hunter-{date_str}.json"
    with open(json_path, "w") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    text_path = DATA_DIR / f"hunter-{date_str}.txt"
    with open(text_path, "w") as f:
        f.write(report_text)

    print(f"\n[+] Saved: {json_path}")
    print(f"[+] Saved: {text_path}")

    total_new = len(new_x) + len(new_btt) + len(new_gh) + len(new_wtm)
    if total_new > 0:
        print(f"\n🚨 发现 {total_new} 个新项目！")

    return report_data


if __name__ == "__main__":
    main()
