import os
import re
import urllib.request
import urllib.parse
from playwright.sync_api import sync_playwright

def send_telegram_notification(message):
    """发送 Telegram 机器人通知"""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("提示: 未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳过 TG 通知。")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        data = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                print("Telegram 通知发送成功。")
            else:
                print(f"Telegram 通知发送失败，状态码: {response.status}")
    except Exception as e:
        print(f"发送 Telegram 通知时发生异常: {e}")

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    raw_cookies = os.environ.get('ACL_COOKIES', '')
    if not raw_cookies:
        msg = "❌ *ACLClouds 自动任务失败*\n原因: 未找到 `ACL_COOKIES` 环境变量。"
        print(msg)
        send_telegram_notification(msg)
        return

    cookies = []
    for item in raw_cookies.split(';'):
        if '=' in item:
            name, value = item.split('=', 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": "dash.aclclouds.com",
                "path": "/"
            })

    context.add_cookies(cookies)
    page = context.new_page()

    status_message = ""
    try:
        print("正在访问项目面板...")
        page.goto("https://dash.aclclouds.com/projects", timeout=60000)
        
        # 充分等待前端框架渲染
        page.wait_for_timeout(6000)

        print("正在保存页面初始截图...")
        page.screenshot(path="debug_page_initial.png", full_page=True)

        log_summary = []

        # ================= 状态 B 拦截检查：检查是否进入【服务器已挂起】全屏弹窗页 =================
        # 锁定法文 "Renouveler maintenant" 或英文 "Renew now" 的紧急续期大按钮
        suspended_btn = page.locator('button').filter(has_text=re.compile(r"Renouveler maintenant|Renew now", re.IGNORECASE))
        
        if suspended_btn.count() > 0 and suspended_btn.first.is_visible():
            print("🚨 状态判定：检测到服务器已过期挂起！正在执行紧急解锁...")
            if suspended_btn.first.is_enabled():
                suspended_btn.first.click(timeout=10000)
                log_summary.append("⚠️ 检测到服务被动挂起，已成功点击大按钮紧急续期")
                print("已点击紧急续期大按钮，等待控制台面板刷新...")
                page.wait_for_timeout(6000)  # 给页面足够的时间刷新出正常的控制台结构
                # 重新截个图记录解锁后的状态
                page.screenshot(path="debug_page_after_suspended_click.png", full_page=True)
        else:
            print("🟢 状态判定：未检测到挂起弹窗，当前处于常规控制台页面。")

        # ================= 状态 A 检查：处理常规控制台下的【提前续期】按钮（最后 2 小时窗口） =================
        # 精确过滤普通的 Renew / Renouveler 按钮
        renew_buttons = page.locator("button").filter(has_text=re.compile(r"^(Renew|Renouveler)$", re.IGNORECASE))
        renew_count = renew_buttons.count()
        clicked_renew = 0

        if renew_count > 0:
            print(f"发现 {renew_count} 个常规续期小按钮，正在检查是否可点击...")
            for i in range(renew_count):
                btn = renew_buttons.nth(i)
                if btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=5000)
                    clicked_renew += 1
                    print(f"已成功点击第 {i+1} 个常规续期按钮。")
                    page.wait_for_timeout(3000)
            if clicked_renew > 0:
                log_summary.append(f"🔄 常规窗口提前续期成功: {clicked_renew} 个服务")

        # ================= 核心保活逻辑：统一检查并处理【Start 启动】按钮 =================
        # 利用绝对不会变动的底层核心属性 [data-variant="start"] 锁定启动键
        start_buttons = page.locator('button[data-variant="start"]')
        start_count = start_buttons.count()
        clicked_start = 0
        skipped_start = 0

        if start_count > 0:
            print(f"正在扫描页面上的所有启动状态（共 {start_count} 个实例）...")
            for i in range(start_count):
                btn = start_buttons.nth(i)
                if btn.is_visible():
                    if btn.is_enabled():
                        # 按钮亮起：说明当前是关机/挂起后的熄火状态，必须点亮它
                        print(f"第 {i+1} 个服务处于停止状态，正在点亮 Start 启动...")
                        btn.click(timeout=10000)
                        clicked_start += 1
                        page.wait_for_timeout(3000)
                    else:
                        # 按钮变灰：说明服务器本身就一直在稳健运行，直接跳过
                        skipped_start += 1
                        print(f"第 {i+1} 个服务正在正常运行中（Start 按钮处于禁用状态），无需操作。")

        # 录入启动通知
        if clicked_start > 0:
            log_summary.append(f"🚀 成功点亮 Start 启动服务: {clicked_start} 个")
        if skipped_start > 0:
            log_summary.append(f"🟢 保持在线（无需重复启动）的服务: {skipped_start} 个")

        # 保存最终执行完的成果截图
        page.screenshot(path="debug_page_final.png", full_page=True)

        # ================= 发送结算通知 =================
        if not log_summary:
            status_message = "⚠️ *ACLClouds 自动化任务提醒*\n当前未在常规续期窗口内，且所有服务均在安全运行中，无需任何操作。"
        else:
            status_message = "✅ *ACLClouds 自动化轮询完毕*\n" + "\n".join(log_summary)

        print("整个复合自动化任务顺利结束。")

    except Exception as e:
        status_message = f"❌ *ACLClouds 自动续期运行出错*\n错误原因: `{str(e)}`"
        print(status_message)
        try:
            page.screenshot(path="error_page.png", full_page=True)
        except:
            pass
    finally:
        browser.close()
        if status_message:
            send_telegram_notification(status_message)

with sync_playwright() as playwright:
    run(playwright)
