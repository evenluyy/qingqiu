import requests
import datetime
import os
import textwrap

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

# === GraphQL 查询模板 ===
query = """
query ($accountTag: string!, $start: DateTime!, $end: DateTime!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      workersInvocationsAdaptive(
        limit: 10000,
        filter: {
          datetime_geq: $start,
          datetime_leq: $end
        },
        orderBy: [datetime_ASC]
      ) {
        dimensions {
          date: datetime
        }
        sum {
          requests
        }
      }
    }
  }
}
"""

def fetch_account_stats(account_id, token):
    """查询单个账号的请求数据"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    variables = {
        "accountTag": account_id,
        "start": start_date.isoformat() + "Z",
        "end": end_date.isoformat() + "Z"
    }

    resp = requests.post(
        "https://api.cloudflare.com/client/v4/graphql",
        json={"query": query, "variables": variables},
        headers=headers
    )

    if resp.status_code != 200:
        raise Exception(f"请求失败 ({resp.status_code}): {resp.text}")

    data = resp.json()
    records = data["data"]["viewer"]["accounts"][0]["workersInvocationsAdaptive"]

    daily_requests = {}
    for item in records:
        date = item["dimensions"]["date"][:10]
        count = item["sum"]["requests"] or 0
        daily_requests[date] = daily_requests.get(date, 0) + count

    return daily_requests


# === 汇总 ===
all_accounts_data = {}
total_per_day = {}

for i, (acc_id, token) in enumerate(zip(ACCOUNT_IDS, API_TOKENS)):
    username = USERNAMES[i] if i < len(USERNAMES) else acc_id
    stats = fetch_account_stats(acc_id, token)
    all_accounts_data[username] = stats
    for d, c in stats.items():
        total_per_day[d] = total_per_day.get(d, 0) + c


# === 输出组装 ===
def format_report(username, stats):
    lines = [f"🧾 账号 {username}:"]
    for date, count in sorted(stats.items()):
        lines.append(f"  {date}: {count:,} 次请求")
    return "\n".join(lines)


reports = []
for username, stats in all_accounts_data.items():
    reports.append(format_report(username, stats))

summary_lines = ["📈 所有账号总计："]
for date, count in sorted(total_per_day.items()):
    summary_lines.append(f"  {date}: {count:,} 次请求")
summary_lines.append(f"\n✅ 合计（{DAYS}天）：{sum(total_per_day.values()):,} 次请求")

# === 输出到控制台 ===
print("📊 cff 每日请求统计（多账号）\n")
print("\n\n".join(reports))
print("\n".join(summary_lines))

# === Telegram 通知 ===
def send_tg_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(tg_url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    })

# 发送逻辑
if TELEGRAM_SPLIT_SEND:
    # 每个账号单独发一条消息
    for username, stats in all_accounts_data.items():
        msg = f"📊 请求统计\n{format_report(username, stats)}"
        send_tg_message(msg)
    send_tg_message("\n".join(summary_lines))
else:
    # 一次性发送全部
    msg = "📊 每日请求统计（多账号）\n\n" + \
          "\n\n".join(reports) + "\n\n" + "\n".join(summary_lines)
    send_tg_message(msg)
