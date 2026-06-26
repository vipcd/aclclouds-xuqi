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
        print("正在访问项目列表面...")
        page.goto("https://dash.aclclouds.com/projects", timeout=60000)
        page.wait_for_timeout(6000) # 等待页面充分加载

        print("保存列表页初始截图...")
        page.screenshot(path="debug_1_projects_list.png", full_page=True)

        log_summary = []

        # ================= 阶段 1：处理全屏挂起拦截（大蓝按钮） =================
        suspended_btn = page.locator('button, a').filter(has_text=re.compile(r"Renouveler maintenant|Renew now", re.IGNORECASE))
        if suspended_btn.count() > 0 and suspended_btn.first.is_visible():
            print("🚨 状态判定：检测到全屏挂起拦截弹窗！正在点击大蓝按钮...")
            if suspended_btn.first.is_enabled():
                suspended_btn.first.click(timeout=10000)
                log_summary.append("⚠️ 检测到服务被动挂起，已点击大蓝按钮解锁")
                page.wait_for_timeout(6000) # 等待页面刷新跳转回列表
                page.screenshot(path="debug_2_after_blue_button.png", full_page=True)

        # ================= 阶段 2：处理列表页面的【Reactivate】重新激活按钮 =================
        reactivate_buttons = page.locator('button, a').filter(has_text=re.compile(r"Reactivate", re.IGNORECASE))
        if reactivate_buttons.count() > 0:
            print(f"⚡ 状态判定：发现需要激活的 Reactivate 按钮！")
            for i in range(reactivate_buttons.count()):
                btn = reactivate_buttons.nth(i)
                if btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=10000)
                    log_summary.append("⚡ 成功点击 Reactivate 按钮重新激活服务")
                    page.wait_for_timeout(6000) # 激活需要后台处理时间
            page.screenshot(path="debug_3_after_reactivate.png", full_page=True)

        # ================= 阶段 3：常规列表页续期检查（防止6小时到期前2小时的续期按钮在列表显示） =================
        renew_list_buttons = page.locator("button").filter(has_text=re.compile(r"^(Renew|Renouveler)$", re.IGNORECASE))
        if renew_list_buttons.count() > 0:
            for i in range(renew_list_buttons.count()):
                btn = renew_list_buttons.nth(i)
                if btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=5000)
                    log_summary.append("🔄 列表页常规窗口提前续期成功")
                    page.wait_for_timeout(3000)

        # ================= 阶段 4【关键核心】：点击 Manage 进入控制台内部 =================
        manage_buttons = page.locator('button, a').filter(has_text=re.compile(r"Manage", re.IGNORECASE))
        if manage_buttons.count() > 0:
            print("🔍 正在点击 Manage 按钮进入服务器内部控制台...")
            manage_buttons.first.click(timeout=10000)
            page.wait_for_timeout(6000) # 等待控制台页面完全加载
            print("已成功进入控制台内部，保存控制台截图...")
            page.screenshot(path="debug_4_console_internal.png", full_page=True)
            
            # 阶段 4.5：在控制台内部也扫描一次常规续期按钮（以防续期按钮只出现在控制台里）
            renew_console_buttons = page.locator("button").filter(has_text=re.compile(r"^(Renew|Renouveler)$", re.IGNORECASE))
            if renew_console_buttons.count() > 0 and renew_console_buttons.first.is_visible() and renew_console_buttons.first.is_enabled():
                renew_console_buttons.first.click(timeout=5000)
                log_summary.append("🔄 控制台内常规窗口提前续期成功")
                page.wait_for_timeout(3000)

            # ================= 阶段 5：在控制台内部统一检查并点亮【Start 启动】按钮 =================
            # 精准匹配绿色的 Start 按钮
            start_buttons = page.locator('button, a').filter(has_text=re.compile(r"Start", re.IGNORECASE))
            if start_buttons.count() > 0 and start_buttons.first.is_visible():
                if start_buttons.first.is_enabled():
                    print("🚀 检测到服务器处于 Offline 熄火状态，正在点击 Start 启动拉起...")
                    start_buttons.first.click(timeout=10000)
                    log_summary.append("🚀 核心保活成功：成功点亮 Start 启动服务！")
                    page.wait_for_timeout(5000) # 等待启动命令下发
                else:
                    print("🟢 服务器已经在正常运行中（Start按钮当前不可点），安全跳过。")
                    log_summary.append("🟢 服务保持在线（无需运行启动）")
            else:
                print("⚠️ 未在控制台页面找到 Start 按钮，请检查控制台权限或结构。")
        else:
            print("❌ 未在项目列表找到 Manage 按钮，无法进入控制台！")
            log_summary.append("❌ 任务异常：未找到进入控制台的 Manage 按钮")

        # 保存最终完结截图
        page.screenshot(path="debug_5_final.png", full_page=True)

        # ================= 阶段 6：组装结算通知 =================
        if not log_summary:
            status_message = "⚠️ *ACLClouds 自动化任务提醒*\n未检测到任何需要处理的异常，服务均在安全运行中。"
        else:
            status_message = "✅ *ACLClouds 自动化闭环运行完毕*\n" + "\n".join(log_summary)

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
