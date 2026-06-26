import os
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
        
        # 等待前端加载
        page.wait_for_timeout(5000)

        print("正在保存页面初始截图...")
        page.screenshot(path="debug_page_initial.png", full_page=True)

        # ================= 逻辑 1：检查并处理【续期 Renew】按钮 =================
        renew_buttons = page.locator("button", has_text="Renew")
        renew_count = renew_buttons.count()
        clicked_renew = 0

        if renew_count > 0:
            print(f"发现 {renew_count} 个续期按钮，正在检查...")
            for i in range(renew_count):
                btn = renew_buttons.nth(i)
                if btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=5000)
                    clicked_renew += 1
                    print(f"已点击第 {i+1} 个 Renew 按钮进行续期。")
                    page.wait_for_timeout(3000)

        # ================= 逻辑 2：检查并处理【启动 Start】按钮（保活） =================
        start_buttons = page.locator("button", has_text="Start")
        start_count = start_buttons.count()
        clicked_start = 0
        skipped_start = 0

        if start_count > 0:
            print(f"发现 {start_count} 个 Start 按钮，正在检查状态...")
            for i in range(start_count):
                btn = start_buttons.nth(i)
                if btn.is_visible():
                    if btn.is_enabled():
                        # 按钮可用：说明服务器处于停止状态，需要拉起
                        print(f"第 {i+1} 个 Start 按钮可点击，检测到服务器已关机，正在尝试拉起...")
                        btn.click(timeout=10000)
                        clicked_start += 1
                        page.wait_for_timeout(3000)
                    else:
                        # 按钮禁用：说明服务器正在运行，不用管它
                        skipped_start += 1
                        print(f"第 {i+1} 个 Start 按钮处于禁用状态（保持启动中），安全跳过。")

        # 最终截图留存
        page.screenshot(path="debug_page_final.png", full_page=True)

        # ================= 逻辑 3：组织无论成功/失败都发送的飞机通知 =================
        log_summary = []
        if clicked_renew > 0:
            log_summary.append(f"🔄 成功续期项目数: {clicked_renew}")
        if clicked_start > 0:
            log_summary.append(f"🚀 检测到关机，已成功拉起服务数: {clicked_start}")
        if skipped_start > 0:
            log_summary.append(f"🟢 正常运行中（无需操作）的服务数: {skipped_start}")
        
        if not log_summary:
            status_message = "⚠️ *ACLClouds 自动化任务提醒*\n未检测到任何需要操作的续期或启动按钮。"
        else:
            status_message = "✅ *ACLClouds 自动化检查完毕*\n" + "\n".join(log_summary)

        print("任务全面执行完毕。")

    except Exception as e:
        status_message = f"❌ *ACLClouds 自动续期运行出错*\n错误原因: `{str(e)}`"
        print(status_message)
        try:
            page.screenshot(path="error_page.png", full_page=True)
        except:
            pass
    finally:
        browser.close()
        # 无论前面发生了什么，这里都会向飞机发通知
        if status_message:
            send_telegram_notification(status_message)

with sync_playwright() as playwright:
    run(playwright)
