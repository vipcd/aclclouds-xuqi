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

        # 1. 寻找并点击续期按钮（严格精确匹配多语言文本）
        print("正在寻找续期按钮...")
        renew_texts = ["Renew", "Renouveler maintenant", "续期"]
        renew_clicked = False
        
        for txt in renew_texts:
            loc = page.get_by_text(txt, exact=True)
            count = loc.count()
            if count > 0:
                print(f"找到 {count} 个精确文本为 '{txt}' 的续期元素，准备点击...")
                for i in range(count):
                    btn = loc.nth(i)
                    if btn.is_visible():
                        btn.click()
                        renew_clicked = True
                        print(f"已点击第 {i+1} 个续期按钮。")
                        page.wait_for_timeout(5000)  # 等待请求处理

        if renew_clicked:
            status_message = "✅ *ACLClouds 自动续期成功*\n已成功点击续期按钮！"
        else:
            print("当前页面未点到续期按钮（可能还未到续期时间）。")
            status_message = "⚠️ *ACLClouds 自动续期提醒*\n未找到或未触发任何续期按钮。"

        # 2. 尝试点击 Manage 按钮进入详情控制台
        #（如果上面点过续期，页面可能会刷新或跳转；如果没点过，我们也需要点 Manage 进去检查开机状态）
        print("正在尝试定位进入详情页的 Manage 按钮...")
        manage_texts = ["Manage", "管理"]
        for txt in manage_texts:
            loc = page.get_by_text(txt, exact=True)
            if loc.count() > 0 and loc.first.is_visible():
                print(f"检测到精确匹配的 '{txt}' 按钮，正在点击进入服务器详情页...")
                loc.first.click()
                page.wait_for_timeout(5000)  # 等待控制台页面完全加载
                break

        # 保存一张当前的最终页面状态截图
        page.screenshot(path="debug_final_state.png", full_page=True)

        # 3. 核心修复：精准检测并点击真正的 Start 按钮（完美避开 Startup 侧边栏）
        print("正在检查服务器运行状态...")
        start_texts = ["Start", "Démarrer", "启动"]
        start_btn = None
        
        for txt in start_texts:
            loc = page.get_by_text(txt, exact=True)
            if loc.count() > 0 and loc.first.is_visible():
                start_btn = loc.first
                break

        if start_btn:
            print("检测到服务器当前处于离线状态，正在尝试点击精准的 'Start' 按钮...")
            start_btn.click()
            print("已点击启动按钮，等待 15 秒让服务器拉起...")
            page.wait_for_timeout(15000)
            
            # 再次保存开机成功后的控制台截图
            page.screenshot(path="debug_after_start.png", full_page=True)
            status_message += "\n🚀 *服务器启动状态*: 检测到离线，已成功精准点击 `Start` 启动服务器！"
        else:
            print("当前页面未检测到可见的开机按钮，服务器可能已经在运行中 (Online)。")
            status_message += "\nℹ️ *服务器启动状态*: 未检测到开机按钮，服务器可能已经在运行中。"

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
        # 最终发送通知
        if status_message:
            send_telegram_notification(status_message)

with sync_playwright() as playwright:
    run(playwright)
