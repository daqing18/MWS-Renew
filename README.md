# MWS-Renew ☁️

MWS ([cloud.puratya.com](https://cloud.puratya.com)) 平台的 Bot / 项目自动续期脚本。通过 Bearer Token 直接调用 MWS API，无需浏览器模拟，轻量高效。

## 功能

- ✅ 自动续期指定 Bot
- ✅ 支持多 Bot 同时续期
- ✅ Telegram 续期结果通知
- ✅ GitHub Actions 定时运行（无需服务器）
- ✅ 自动清理旧 Workflow 运行记录

## 原理

MWS 平台提供 REST API，通过 `SESSION_TOKEN`（Bearer Token）认证。脚本直接调用 `POST /bots/{id}/renew` 接口续期，比浏览器模拟更稳定、更快。

## 前置准备

### 1. 获取 SESSION_TOKEN（Bearer Token）

> ⚠️ **Token 有效期不定**，过期后需重新获取并更新 GitHub Secrets。

**方法一：浏览器 DevTools（推荐）**

1. 打开 [cloud.puratya.com](https://cloud.puratya.com) 并登录（Discord 登录）
2. 按 `F12` 打开开发者工具 → 切换到 **Application** / **存储** 标签
3. 左侧找到 **Local Storage** → 点击 `https://cloud.puratya.com`
4. 找到键为 `session_token` 或 `token` 的条目，复制其值
5. 这个值就是你的 `SESSION_TOKEN`

**方法二：从网络请求获取**

1. 登录后按 `F12` → **Network** 标签
2. 刷新页面，筛选 `auth/me` 或 `bots/` 的请求
3. 点击任意请求 → **Headers** → **Request Headers** → 找到 `Authorization: Bearer xxx`
4. 复制 `xxx` 部分

**方法三：curl 命令行验证**

```bash
# 替换 YOUR_TOKEN 为获取到的值
curl -H "Authorization: Bearer YOUR_TOKEN" https://cloud-api.puratya.com/auth/me
```

返回类似以下内容即表示 Token 有效：
```json
{"id":123,"username":"your_name","email":"...","plan":"free"}
```

### 2. 获取 Bot ID

1. 登录 [cloud.puratya.com](https://cloud.puratya.com)
2. 进入你的 Bot 详情页
3. 查看 URL：`https://cloud.puratya.com/bots/9329` — 最后的数字 `9329` 就是 Bot ID
4. 或者直接用 API 查询：
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" https://cloud-api.puratya.com/bots
   ```

## 配置参数

### 环境变量 / GitHub Secrets

| Secret | 必填 | 说明 |
|--------|------|------|
| `SESSION_TOKEN` | ✅ | MWS 登录后的 Bearer Token，见上方获取方法 |
| `GH_TOKEN` | ❌ | GitHub Personal Access Token（用于自动更新 Secrets，可选） |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token，用于发送通知 |
| `TG_CHAT_ID` | ❌ | Telegram 聊天 ID，接收通知 |

### 脚本内配置（`mws_renew.py`）

在脚本开头的 **配置区域** 修改：

```python
API_BASE = "https://cloud-api.puratya.com"     # API 地址，一般不动
BOT_IDS = [9329]                                 # 要续期的 Bot ID 列表
```

> 多个 Bot：`BOT_IDS = [9329, 9330, 9331]`

## 部署方式

### GitHub Actions（推荐）

1. **Fork 或 Push 到你的仓库**：`jacksun-king/MWS-Renew` → 你的仓库
2. **添加 Secrets**：
   - 仓库 → **Settings** → **Secrets and variables** → **Actions**
   - 添加 `SESSION_TOKEN`（必填）
   - 可选添加 `TG_BOT_TOKEN` + `TG_CHAT_ID`（Telegram 通知）
3. **修改 Bot ID**（可选）：
   - 编辑 `mws_renew.py` 中的 `BOT_IDS` 列表
4. **运行方式**：
   - **自动**：每天 UTC 10:00（北京时间 18:00）自动运行
   - **手动**：仓库 → **Actions** → **MWS Auto Renew** → **Run workflow**

### 本地运行

```bash
pip install requests
export SESSION_TOKEN="your_token_here"
export TG_BOT_TOKEN="your_bot_token"   # 可选
export TG_CHAT_ID="your_chat_id"       # 可选
python3 mws_renew.py
```

## 续期频率建议

MWS 免费 Bot 通常有运行时长限制（如 12 小时/24 小时），建议：

- 免费计划：每天运行 1 次（cron: `0 10 * * *` = 北京时间 18:00）
- 如果 Bot 运行时长短，可改为每天 2 次（`0 2,14 * * *`）

> ⚠️ 不要过于频繁续期，以免触发平台风控。

## 效果

运行成功后，Telegram 会收到通知：

```
☁️ MWS Bot 续期通知

✅ 续期成功
🤖 Bot: my-bot-name
⏱️ 剩余时间: 12h
📅 到期时间: 2026-08-11T06:00:00Z
⏰ 执行时间: 2026-08-10 18:00:00
```

## 其他

- 本项目参考了 `Katabump-Renew`、`myByteNut` 等续期脚本的模式
- 与浏览器模拟方案不同，本脚本使用 **API Token 直调**，更轻量、更稳定
- 如 Token 过期，按上方方法重新获取并更新 GitHub Secrets 即可