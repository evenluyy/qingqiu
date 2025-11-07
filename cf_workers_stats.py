import requests
import datetime
import os

# === 从环境变量读取配置 ===
ACCOUNT_IDS = [x.strip() for x in os.environ.get("CF_ACCOUNT_IDS", "").split(",") if x.strip()]
API_TOKENS = [x.strip() for x in os.environ.get("CF_API_TOKENS", "").split(",") if x.strip()]
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DAYS = int(os.environ.get("DAYS", "7"))

if len(ACCOUNT_IDS) != len(API_TOKENS):
    raise ValueError("⚠️ CF_ACCOUNT_IDS 与 CF_API_TOKENS 数量不一致，请一一对应。")

# === 时间范围 ===
end_date = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
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

# === 汇总所有账号 ===
all_accounts_data = {}
total_per_day = {}

for acc_id, token in zip(ACCOUNT_IDS, API_TOKENS):
    stats = fetch_account_stats(acc_id, token)
    all_accounts_data[acc_id] = stats
    for d, c in stats.items():
        total_per_day[d] = total_per_day.get(d, 0) + c

# === 格式化输出 ===
output_lines = ["📊 Cloudflare Workers 每日请求统计（多账号）\n"]
for acc_id, stats in all_accounts_data.items():
    output_lines.append(f"🧾 账号 {acc_id}:")
    for date, count in sorted(stats.items()):
        output_lines.append(f"  {date}: {count:,} 次请求")
    output_lines.append("")

output_lines.append("📈 所有账号总计：")
for date, count in sorted(total_per_day.items()):
    output_lines.append(f"  {date}: {count:,} 次请求")

output_lines.append(f"\n✅ 合计（{DAYS}天）：{sum(total_per_day.values()):,} 次请求")

output_text = "\n".join(output_lines)
print(output_text)

# === 发送到 Telegram ===
if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(tg_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": output_text})
