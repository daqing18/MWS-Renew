#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# 模板名称：MWS Token 续期脚本（增强版）
# 描述：通过 Bearer Token 直接调用 MWS API 执行续期操作，
#       自动检测 Token 过期时间并提醒，支持通过 GH_TOKEN
#       自动更新 GitHub Secrets 中的 SESSION_TOKEN。
# 归类：TOKEN 类型（基于模板 3 改造 + 自动更新功能）
# ============================================================

import os, sys, time, json, base64, requests, subprocess
from datetime import datetime, timezone, timedelta

# ============================================================
# 📌 配置区域 (一般不需要修改)
# ============================================================
API_BASE = "https://cloud-api.puratya.com"
# Token 剩余天数低于此值时发提醒（默认 7 天）
TOKEN_WARN_DAYS = int(os.environ.get("TOKEN_WARN_DAYS") or "7")
# ============================================================

# 全局配置
GH_TOKEN      = os.environ.get("GH_TOKEN") or ""
TG_CHAT_ID    = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN  = os.environ.get("TG_BOT_TOKEN") or ""
# 手动传入的新 Token（通过 workflow_dispatch 输入）
NEW_TOKEN     = os.environ.get("NEW_TOKEN") or ""

# ---------- 多账号检测 ----------
# 账号1: SESSION_TOKEN_1 + BOT_IDS_1
# 账号2: SESSION_TOKEN_2 + BOT_IDS_2
# ...
# 向下兼容: SESSION_TOKEN + BOT_IDS（单账号）
ACCOUNTS = []
for i in range(1, 100):
    token = os.environ.get(f"SESSION_TOKEN_{i}")
    if token:
        bot_ids_raw = os.environ.get(f"BOT_IDS_{i}") or "9447"
        print(f"🐛 [DEBUG] 账号{i}: env BOT_IDS_{i}='{repr(os.environ.get(f'BOT_IDS_{i}'))}', 最终 bot_ids_raw='{bot_ids_raw}'")
        bot_ids = [int(x.strip()) for x in bot_ids_raw.split(",") if x.strip()]
        if not bot_ids:
            print(f"⚠️ 账号{i} BOT_IDS 配置为空，使用默认值 9447")
            bot_ids = [9447]
        ACCOUNTS.append({"token": token, "bot_ids": bot_ids, "label": f"账号{i}"})
    else:
        break

if not ACCOUNTS:
    legacy_token = os.environ.get("SESSION_TOKEN") or ""
    if legacy_token:
        bot_ids_raw = os.environ.get("BOT_IDS") or "9447"
        bot_ids = [int(x.strip()) for x in bot_ids_raw.split(",") if x.strip()]
        if not bot_ids:
            bot_ids = [9447]
        ACCOUNTS.append({"token": legacy_token, "bot_ids": bot_ids, "label": "默认账号"})

if not ACCOUNTS:
    print("❌ 未配置任何 SESSION_TOKEN，脚本终止。")
    print("   单账号: 设置 SESSION_TOKEN")
    print("   多账号: 设置 SESSION_TOKEN_1, SESSION_TOKEN_2, ...")
    sys.exit(1)

print(f"📋 检测到 {len(ACCOUNTS)} 个账号: {', '.join(a['label'] for a in ACCOUNTS)}")

AUTH_HEADER = {}  # 占位，main() 循环中赋值

# ------------------------------------------------------------
# JWT Token 解析与过期检测
# ------------------------------------------------------------
def decode_jwt(token: str):
    """解析 JWT，返回 payload dict；失败返回 None"""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        # base64url 补全 padding
        padding = "=" * (-len(payload) % 4)
        payload += padding
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception as e:
        print(f"⚠️ Token 解析失败(非JWT格式?): {e}")
        return None

def token_expire_info(token: str):
    """返回 (剩余天数, 过期时间str)；无法解析返回 (None, None)"""
    payload = decode_jwt(token)
    if not payload or "exp" not in payload:
        return None, None
    exp_ts = payload["exp"]
    now_ts = int(time.time())
    remain_days = (exp_ts - now_ts) / 86400
    exp_str = datetime.fromtimestamp(exp_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return remain_days, exp_str

# ------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------
def update_github_secret(secret_name, new_value):
    if not GH_TOKEN:
        print(f"⚠️ 未配置 GH_TOKEN，无法自动更新 Secret {secret_name}")
        return False
    if not new_value:
        print(f"⚠️ 跳过更新 {secret_name}：新值为空")
        return False
    masked = new_value[:6] + "..." + new_value[-6:] if len(new_value) > 12 else "***"
    print(f"🔄 更新 Secret: {secret_name} (新值: {masked})")
    try:
        env = os.environ.copy()
        env["GH_TOKEN"] = GH_TOKEN
        proc = subprocess.run(
            ["gh", "secret", "set", secret_name, "--body", new_value, "--repo", os.environ.get("GITHUB_REPOSITORY", "")] if os.environ.get("GITHUB_REPOSITORY") else
            ["gh", "secret", "set", secret_name, "--body", new_value],
            capture_output=True, text=True, timeout=60, check=False, env=env
        )
        if proc.returncode == 0:
            print(f"✅ {secret_name} 更新成功")
            return True
        else:
            print(f"❌ 更新失败: {proc.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False

def send_telegram(message: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ Telegram 未配置，跳过通知")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message}, timeout=10)
        print("✅ Telegram 通知已发送")
    except Exception as e:
        print(f"❌ Telegram 发送失败: {e}")

def format_notification(status: str, bot_name: str, remaining: str, stop_at: str) -> str:
    now = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "☁️ MWS Bot 续期通知",
        "",
        f"{status}",
        f"🤖 Bot: {bot_name}",
        f"⏱️ 剩余时间: {remaining}",
        f"📅 到期时间: {stop_at}",
        f"⏰ 执行时间: {now}",
    ]
    return "\n".join(lines)

# ------------------------------------------------------------
# 获取用户信息
# ------------------------------------------------------------
def get_user_info():
    print("👤 获取用户信息...")
    resp = requests.get(f"{API_BASE}/auth/me", headers=AUTH_HEADER, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    print(f"   用户: {data.get('username')} (ID: {data.get('id')})")
    return data

# ------------------------------------------------------------
# 获取 Bot 信息
# ------------------------------------------------------------
def get_bot_info(bot_id: int):
    print(f"🔍 获取 Bot {bot_id} 信息...")
    resp = requests.get(f"{API_BASE}/bots/{bot_id}", headers=AUTH_HEADER, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    timer = data.get("timer", {})
    print(f"   名称: {data.get('name')}")
    print(f"   状态: {data.get('status')}")
    print(f"   剩余: {timer.get('remaining_hours')}h / {timer.get('remaining_seconds')}s")
    print(f"   到期: {timer.get('stop_at')}")
    return data

# ------------------------------------------------------------
# 续期 Bot
# ------------------------------------------------------------
def renew_bot(bot_id: int) -> dict:
    print(f"🔄 续期 Bot {bot_id}...")
    resp = requests.post(f"{API_BASE}/bots/{bot_id}/renew", headers=AUTH_HEADER, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    timer = data.get("timer", {})
    print(f"   ✅ 续期成功!")
    print(f"   剩余: {timer.get('remaining_hours')}h / {timer.get('remaining_seconds')}s")
    print(f"   到期: {timer.get('stop_at')}")
    return data

# ------------------------------------------------------------
# Token 生命周期处理：检测 + 提醒 + 自动更新 Secrets
# ------------------------------------------------------------
def handle_token_lifecycle(existing_token, secret_name):
    """
    处理 Token 生命周期：
    1. 如果有 NEW_TOKEN，自动更新 Secret 并使用新 token
    2. 否则检测现有 token 剩余天数，快过期/已过期时发 TG 提醒
    返回实际要使用的 token
    """
    # 情况1：用户手动传入了新 token（通过 workflow_dispatch）
    if NEW_TOKEN:
        print(f"🔄 检测到手动传入的新 Token，准备更新 Secret: {secret_name}")
        ok = update_github_secret(secret_name, NEW_TOKEN)
        if ok:
            send_telegram(
                f"🔑 MWS Token 自动更新成功\n\n"
                f"Secret: `{secret_name}` 已更新\n"
                f"触发来源: 手动 workflow_dispatch\n\n"
                f"MWS Auto Renewal"
            )
            return NEW_TOKEN
        else:
            print(f"⚠️ Secret 更新失败，本次使用新 Token 直接续期（下次运行仍会失效）")
            return NEW_TOKEN

    # 情况2：检测现有 token 剩余天数
    remain_days, exp_str = token_expire_info(existing_token)
    if remain_days is None:
        print(f"⚠️ 无法解析 Token 过期时间，跳过过期提醒")
        return existing_token

    print(f"⏳ Token 剩余: {remain_days:.1f} 天 (到期: {exp_str})")

    if remain_days <= 0:
        # Token 已过期
        msg = (
            f"❌ MWS Token 已过期\n\n"
            f"到期时间: {exp_str}\n"
            f"Secret: `{secret_name}`\n\n"
            f"请重新登录 cloud.puratya.com，从浏览器 Cookie "
            f"`__Host-mrtcloud_token` 复制新值，然后手动触发 "
            f"MWS Auto Renew workflow 并填入 NEW_TOKEN\n\n"
            f"MWS Auto Renewal"
        )
        print(f"❌ Token 已过期，发送提醒")
        send_telegram(msg)
    elif remain_days <= TOKEN_WARN_DAYS:
        # 即将过期
        msg = (
            f"⚠️ MWS Token 即将过期\n\n"
            f"剩余: {remain_days:.1f} 天\n"
            f"到期时间: {exp_str}\n"
            f"Secret: `{secret_name}`\n\n"
            f"请重新登录 cloud.puratya.com，从浏览器 Cookie "
            f"`__Host-mrtcloud_token` 复制新值，然后手动触发 "
            f"MWS Auto Renew workflow 并填入 NEW_TOKEN\n\n"
            f"MWS Auto Renewal"
        )
        print(f"⚠️ Token 将在 {remain_days:.1f} 天后过期，发送提醒")
        send_telegram(msg)

    return existing_token

# ------------------------------------------------------------
# 主入口
# ------------------------------------------------------------
def main():
    global AUTH_HEADER
    print("=" * 40)
    print("  MWS Bot 自动续期（增强版）")
    print("=" * 40)

    all_results = []
    for idx, acc in enumerate(ACCOUNTS):
        label = acc["label"]
        secret_name = f"SESSION_TOKEN_{idx+1}" if idx > 0 else "SESSION_TOKEN"
        legacy = False
        # 兼容旧版命名：账号1 可能配的是 SESSION_TOKEN 而不是 SESSION_TOKEN_1
        if idx == 0 and not os.environ.get("SESSION_TOKEN_1") and os.environ.get("SESSION_TOKEN"):
            secret_name = "SESSION_TOKEN"
        elif idx == 0:
            secret_name = "SESSION_TOKEN_1"

        # Token 生命周期处理
        token = handle_token_lifecycle(acc["token"], secret_name)
        AUTH_HEADER = {"Authorization": f"Bearer {token}"}
        print(f"\n{'=' * 40}")
        print(f"  {label}")
        print(f"{'=' * 40}")

        try:
            user = get_user_info()
        except Exception as e:
            print(f"❌ {label} 获取用户信息失败: {e}")
            send_telegram(f"❌ MWS {label} 续期失败\n无法获取用户信息: {e}")
            continue

        for bot_id in acc["bot_ids"]:
            try:
                bot_before = get_bot_info(bot_id)
                result = renew_bot(bot_id)

                timer = result.get("timer", {})
                info = {
                    "name": bot_before.get("name", f"Bot-{bot_id}"),
                    "status": "✅ 续期成功",
                    "remaining": f"{timer.get('remaining_hours', 0)}h",
                    "stop_at": timer.get("stop_at", "未知"),
                }
            except Exception as e:
                print(f"❌ {label} Bot {bot_id} 续期失败: {e}")
                info = {
                    "name": f"Bot-{bot_id}",
                    "status": "❌ 续期失败",
                    "remaining": "N/A",
                    "stop_at": str(e)[:50],
                }
            info["label"] = label
            all_results.append(info)

            msg = format_notification(info["status"], f"[{label}] {info['name']}", info["remaining"], info["stop_at"])
            send_telegram(msg)

    # 汇总
    success = sum(1 for r in all_results if "成功" in r["status"])
    fail = sum(1 for r in all_results if "失败" in r["status"])
    accounts = len(set(r["label"] for r in all_results))
    print(f"\n📊 汇总: {accounts} 个账号, {success} 成功, {fail} 失败, 共 {len(all_results)} 个 Bot")

if __name__ == "__main__":
    main()
