import requests
import datetime
import os

# === 从环境变量读取配置 ===
API_TOKEN = os.environ.get("CF_API_TOKEN")
ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DAYS = int(os.environ.get("DAYS", "7"))

# === 时间计算 ===
end_date = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
start_date = end_date - datetime.timedelta(days=DAYS)

# === GraphQL 查询 ===
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

variables = {
    "accountTag": ACCOUNT_ID,
    "start": start_date.isoformat() + "Z",
    "end": end_date.isoformat() + "Z"
}

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# === 调用 API ===
response = requests.post(
    "https://api.cloudflare.com/client/v4/graphql",
    json={"query": query, "variables": variables},
    headers=headers
)

data = response.json()
records = data["data"]["viewer"]["accounts"][0]["workersInvocationsAdaptive"]

# === 汇总请求数 ===
daily_requests = {}
for item in records:
    date = item["dimensions"]["date"][:10]
    count = item["sum"]["requests"] or 0
    daily_requests[date] = daily_requests.get(date, 0) + count

# === 格式化输出 ===
output_lines = ["📊 Cloudflare Workers 每日请求统计："]
for date, count in sorted(daily_requests.items()):
    output_lines.append(f"{date}: {count:,} 次请求")

output_text = "\n".join(output_lines)
print(output_text)

# === 发送到 Telegram ===
if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(tg_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": output_text})
