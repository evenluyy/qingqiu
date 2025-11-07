# qingqiu

Secrets 配置示例
Secret 名称	示例值	说明
CF_ACCOUNT_IDS	accid1,accid2,accid3	Cloudflare 账号 ID
CF_API_TOKENS	token1,token2,token3	每个账号对应的 API Token
CF_USERNAMES	主站,博客,测试环境	自定义别名
TELEGRAM_BOT_TOKEN	123456:ABCxyz	Telegram 机器人 Token
TELEGRAM_CHAT_ID	-1001234567890	群聊或私聊 ID
TELEGRAM_SPLIT_SEND	true	每个账号分条发送（或 false）

你需要准备的东西

在运行脚本前，请先准备好两项信息：

Cloudflare API Token

前往 https://dash.cloudflare.com/profile/api-tokens

点击 “Create Token”

选择模板 “Read analytics” 或手动授予权限：

Account → Workers Scripts → Read

Account → Account Settings → Read

保存生成的 token。

Account ID

登录 Cloudflare 控制台。

打开任意 Worker，右侧或顶部可以看到 Account ID。
