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
    is_in_detail_page = False # 标记是否已经进入了详情页
    
    try:
        print("正在访问项目面板...")
        page.goto("https://dash.aclclouds.com/projects", timeout=60000)
        
        page.wait_for_timeout(5000)

        print("正在保存页面截图以供排查...")
        page.screenshot(path="debug_page.png", full_page=True)
        print("截图保存成功: debug_page.png")

        print("正在寻找续期按钮...")
        # 定义可能出现的续期按钮选择器
        target_selectors = [
            "button:has-text('Renew')", "a:has-text('Renew')",
            "button:has-text('Renouveler')", "a:has-text('Renouveler')",
            "button:has-text('续期')", "a:has-text('续期')"
        ]
        
        renew_buttons = page.locator(", ".join(target_selectors))
        count = renew_buttons.count()

        # 如果在列表页没找到续期按钮，尝试检查是不是需要点击 "Manage" 进入详情页
        if count == 0:
            manage_btn = page.locator("button:has-text('Manage'), a:has-text('Manage'), button:has-text('管理'), a:has-text('管理')").first
            if manage_btn.is_visible():
                print("未在列表页找到续期按钮，但检测到 'Manage' 按钮。正在尝试进入服务器详情页...")
                manage_btn.click()
                page.wait_for_timeout(5000)  # 等待详情页/控制台加载
                is_in_detail_page = True
                
                # 重新保存一张进入详情页后的截图方便排查
                page.screenshot(path="debug_detail_page.png", full_page=True)
                
                # 重新获取详情页里的续期按钮
                renew_buttons = page.locator(", ".join(target_selectors))
                count = renew_buttons.count()
        else:
            # 如果在列表页就有点到续期，点完后我们需要主动进一下详情页去启动服务器
            pass

        # 执行续期点击
        renew_clicked = False
        if count == 0:
            print("未找到任何续期按钮。可能还未到允许续期的系统时间（到期前2小时内）。")
            status_message = "⚠️ *ACLClouds 自动续期提醒*\n未找到任何续期按钮。可能还未到允许续期的系统时间。"
        else:
            print(f"找到 {count} 个续期元素，准备点击...")
            for i in range(count):
                button = renew_buttons.nth(i)
                if button.is_visible():
                    button.click()
                    renew_clicked = True
                    print(f"已点击第 {i+1} 个续期按钮。")
                    page.wait_for_timeout(5000)
            status_message = f"✅ *ACLClouds 自动续期成功*\n已成功点击续期按钮！"

        # 如果刚才没有进详情页，但现在我们需要去检查服务器启动状态，就进一下详情页
        if not is_in_detail_page:
            manage_btn = page.locator("button:has-text('Manage'), a:has-text('Manage'), button:has-text('管理'), a:has-text('管理')").first
            if manage_btn.is_visible():
                manage_btn.click()
                page.wait_for_timeout(5000)
                is_in_detail_page = True

        # ---- 核心新增：自动检测并点击 Start 按钮 ----
        if is_in_detail_page:
            print("正在检查服务器运行状态...")
            # 兼容多语言的 Start 按钮定位器
            start_selectors = [
                "button:has-text('Start')", "a:has-text('Start')",
                "button:has-text('Démarrer')", "a:has-text('Démarrer')", # 法语的启动
                "button:has-text('启动')", "a:has-text('启动')"
            ]
            start_btn = page.locator(", ".join(start_selectors)).first
            
            # 只有当 Start 按钮存在且可见时（代表当前是 Offline 状态），才去点它
            if start_btn.is_visible():
                print("检测到服务器当前处于离线状态，正在尝试点击 'Start' 启动服务器...")
                start_btn.click()
                print("已点击启动按钮，等待10秒让服务器拉起...")
                page.wait_for_timeout(10000) # 多等一会让服务器开机
                
                page.screenshot(path="debug_after_start.png", full_page=True)
                status_message += "\n🚀 *服务器启动状态*: 检测到离线，已自动点击 `Start` 启动服务器！"
            else:
                print("未检测到 'Start' 按钮，服务器可能已经在运行中 (Online)。")
                status_message += "\nℹ️ *服务器启动状态*: 未检测到开机按钮，服务器可能已经在运行中。"
        else:
            status_message += "\n⚠️ *服务器启动状态*: 无法进入详情页，跳过开机检查。"

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
