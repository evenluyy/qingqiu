import requests
import datetime
import os
import time
# === 环境变量 ===
ACCOUNT_IDS = [x.strip() for x in os.environ.get("CF_ACCOUNT_IDS", "").split(",") if x.strip()]
API_TOKENS = [x.strip() for x in os.environ.get("CF_API_TOKENS", "").split(",") if x.strip()]
USERNAMES = [x.strip() for x in os.environ.get("CF_USERNAMES", "").split(",") if x.strip()]
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_SPLIT_SEND = os.environ.get("TELEGRAM_SPLIT_SEND", "false").lower() == "true"
DAYS = int(os.environ.get("DAYS", "7"))

# === 校验 ===
if len(ACCOUNT_IDS) != len(API_TOKENS):
    raise ValueError("⚠️ CF_ACCOUNT_IDS 与 CF_API_TOKENS 数量必须一致。")

if USERNAMES and len(USERNAMES) != len(ACCOUNT_IDS):
    raise ValueError("⚠️ CF_USERNAMES 数量必须与 CF_ACCOUNT_IDS 一致（或留空）。")

# === 时间范围 ===
end_date = datetime.datetime.utcnow()  # 包含今天
start_date = end_date - datetime.timedelta(days=DAYS)

# === GraphQL 查询（包含 Workers + Pages） ===
graphql_query = """
query getWorkersAndPagesMetrics($accountId: string!, $start: DateTime!, $end: DateTime!) {
  viewer {
    accounts(filter: {accountTag: $accountId}) {
      workersInvocationsAdaptive(
        limit: 10000,
        filter: {
          datetime_geq: $start,
          datetime_leq: $end
        },
        orderBy: [datetime_ASC]
      ) {
        dimensions { date: datetime }
        sum { requests }
      }
      pagesFunctionsInvocationsAdaptiveGroups(
        limit: 10000,
        filter: {
          datetime_geq: $start,
          datetime_leq: $end
        },
        orderBy: [datetime_ASC]
      ) {
        dimensions { date: datetime }
        sum { requests }
      }
    }
  }
}



def fetch_account_stats(account_id, token, max_retries=3):
    """查询单个账号的 Workers + Pages 数据（带容错重试）"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    variables = {
        "accountId": account_id,
        "start": start_date.isoformat() + "Z",
        "end": end_date.isoformat() + "Z"
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                "https://api.cloudflare.com/client/v4/graphql",
                json={"query": graphql_query, "variables": variables},
                headers=headers,
                timeout=30
            )

            # 检查 HTTP 状态
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

            data = resp.json()

            # 检查 GraphQL 错误
            if data.get("errors"):
                raise Exception(f"GraphQL errors: {data['errors']}")

            viewer = data.get("data", {}).get("viewer")
            if not viewer or not viewer.get("accounts"):
                raise Exception("Cloudflare 返回空 data 或 accounts。")

            account_data = viewer["accounts"][0]
            break  # ✅ 成功，跳出循环

        except Exception as e:
            print(f"⚠️ 第 {attempt}/{max_retries} 次请求失败：{e}")
            if attempt == max_retries:
                raise
            time.sleep(3 * attempt)  # 逐次延迟重试

    # === 数据提取部分 ===
    workers_data = account_data.get("workersInvocationsAdaptive", [])
    pages_data = account_data.get("pagesFunctionsInvocationsAdaptiveGroups", [])

    def daily_sum(items):
        result = {}
        for i in items:
            date = i["dimensions"]["date"][:10]
            result[date] = result.get(date, 0) + (i["sum"]["requests"] or 0)
        return result

    workers_daily = daily_sum(workers_data)
    pages_daily = daily_sum(pages_data)

    combined_daily = {
        d: workers_daily.get(d, 0) + pages_daily.get(d, 0)
        for d in set(workers_daily) | set(pages_daily)
    }

    return {"workers": workers_daily, "pages": pages_daily, "combined": combined_daily}


# === 汇总 ===
all_accounts_data = {}
total_combined = {}

for i, (acc_id, token) in enumerate(zip(ACCOUNT_IDS, API_TOKENS)):
    username = USERNAMES[i] if i < len(USERNAMES) else acc_id
    stats = fetch_account_stats(acc_id, token)
    all_accounts_data[username] = stats
    for d, c in stats["combined"].items():
        total_combined[d] = total_combined.get(d, 0) + c

# === 输出组装 ===
def format_account_report(username, stats):
    lines = [f"🧾 账号 {username}:"]
    dates = sorted(stats["combined"].keys())
    for date in dates:
        w = stats["workers"].get(date, 0)
        p = stats["pages"].get(date, 0)
        lines.append(f"  {date}: Workers {w:,} | Pages {p:,} | 合计 {(w + p):,}")
    total_w = sum(stats["workers"].values())
    total_p = sum(stats["pages"].values())
    lines.append(f"  ➤ 总计：Workers {total_w:,} + Pages {total_p:,} = {(total_w + total_p):,}")
    return "\n".join(lines)

reports = [format_account_report(u, s) for u, s in all_accounts_data.items()]

summary_lines = ["📈 所有账号总计："]
for date, count in sorted(total_combined.items()):
    summary_lines.append(f"  {date}: {count:,} 次请求")
summary_lines.append(f"\n✅ 合计（{DAYS}天）：{sum(total_combined.values()):,} 次请求")

output_text = "📊 Cloudflare Workers & Pages 每日请求统计\n\n" + "\n\n".join(reports) + "\n\n" + "\n".join(summary_lines)

print(output_text)

# === Telegram 发送 ===
def send_tg_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(tg_url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    })

if TELEGRAM_SPLIT_SEND:
    for username, stats in all_accounts_data.items():
        send_tg_message(format_account_report(username, stats))
    send_tg_message("\n".join(summary_lines))
else:
    send_tg_message(output_text)
