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
        msg = "❌ *ACLClouds 自动续期失败*\n原因: 未找到 `ACL_COOKIES` 环境变量。"
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
        
        page.wait_for_timeout(5000)

        print("正在保存页面截图以供排查...")
        page.screenshot(path="debug_page.png", full_page=True)
        print("截图保存成功: debug_page.png")

        renew_buttons = page.locator("text='Renew'")
        count = renew_buttons.count()

        if count == 0:
            status_message = "⚠️ *ACLClouds 自动续期提醒*\n未找到 'Renew' 按钮。可能是没有到期需要续期的项目。请检查 GitHub Actions 页面下载的截图确认状态。"
            print("未找到 'Renew' 按钮。")
        else:
            print(f"找到 {count} 个 'Renew' 元素，准备点击...")
            clicked_count = 0
            for i in range(count):
                button = renew_buttons.nth(i)
                if button.is_visible():
                    button.click()
                    clicked_count += 1
                    print(f"已点击第 {i+1} 个 Renew 按钮。")
                    page.wait_for_timeout(3000) 
            
            page.screenshot(path="debug_page_after_click.png", full_page=True)
            status_message = f"✅ *ACLClouds 自动续期成功*\n检测到 {count} 个续期元素，已成功点击 {clicked_count} 个按钮！"

        print("任务执行完毕。")

    except Exception as e:
        status_message = f"❌ *ACLClouds 自动续期运行出错*\n错误信息: `{str(e)}`"
        print(status_message)
        try:
            page.screenshot(path="error_page.png", full_page=True)
        except:
            pass
    finally:
        browser.close()
        # 无论成功失败，最终发送通知
        if status_message:
            send_telegram_notification(status_message)

with sync_playwright() as playwright:
    run(playwright)
