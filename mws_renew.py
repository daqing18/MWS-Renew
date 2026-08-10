#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# 模板名称：MWS Token 续期脚本
# 描述：通过 Bearer Token 直接调用 MWS API 执行续期操作，
#       并自动更新 GitHub Secrets 中的 SESSION_TOKEN。
# 归类：TOKEN 类型（基于模板 3 改造）
# ============================================================

import os, sys, time, json, requests, subprocess
from datetime import datetime, timezone, timedelta

# ============================================================
# 📌 配置区域 (必须修改)
# ============================================================
API_BASE = "https://cloud-api.puratya.com"
BOT_IDS = [9329]  # 要续期的 Bot ID 列表
# ============================================================

# 环境变量（与 Secrets 对应）
SESSION_TOKEN = os.environ.get("SESSION_TOKEN") or ""
GH_TOKEN      = os.environ.get("GH_TOKEN") or ""
TG_CHAT_ID    = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN  = os.environ.get("TG_BOT_TOKEN") or ""

if not SESSION_TOKEN:
    print("❌ 未配置 SESSION_TOKEN，脚本终止。")
    sys.exit(1)

AUTH_HEADER = {"Authorization": f"Bearer {SESSION_TOKEN}"}

# ------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------
def update_github_secret(secret_name, new_value):
    if not new_value:
        print(f"⚠️ 跳过更新 {secret_name}：新值为空")
        return False
    masked = new_value[:4] + "..." + new_value[-4:] if len(new_value) > 8 else "***"
    print(f"🔄 更新 Secret: {secret_name} (新值: {masked})")
    try:
        env = os.environ.copy()
        if GH_TOKEN:
            env["GH_TOKEN"] = GH_TOKEN
        proc = subprocess.run(
            ["gh", "secret", "set", secret_name, "--body", new_value],
            capture_output=True, text=True, timeout=30, check=False, env=env
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
# 主入口
# ------------------------------------------------------------
def main():
    print("=" * 40)
    print("  MWS Bot 自动续期")
    print("=" * 40)

    try:
        user = get_user_info()
    except Exception as e:
        print(f"❌ 获取用户信息失败: {e}")
        send_telegram(f"❌ MWS 续期失败\n无法获取用户信息: {e}")
        sys.exit(1)

    results = []
    for bot_id in BOT_IDS:
        try:
            bot_before = get_bot_info(bot_id)
            result = renew_bot(bot_id)
            bot_after = get_bot_info(bot_id)

            timer = result.get("timer", {})
            results.append({
                "name": bot_before.get("name", f"Bot-{bot_id}"),
                "status": "✅ 续期成功",
                "remaining": f"{timer.get('remaining_hours', 0)}h",
                "stop_at": timer.get("stop_at", "未知"),
            })
        except Exception as e:
            print(f"❌ Bot {bot_id} 续期失败: {e}")
            results.append({
                "name": f"Bot-{bot_id}",
                "status": "❌ 续期失败",
                "remaining": "N/A",
                "stop_at": str(e)[:50],
            })

    # 发送通知
    for r in results:
        msg = format_notification(r["status"], r["name"], r["remaining"], r["stop_at"])
        send_telegram(msg)

    # 汇总
    success = sum(1 for r in results if "成功" in r["status"])
    fail = sum(1 for r in results if "失败" in r["status"])
    print(f"\n📊 汇总: {success} 成功, {fail} 失败, 共 {len(results)} 个 Bot")

if __name__ == "__main__":
    main()