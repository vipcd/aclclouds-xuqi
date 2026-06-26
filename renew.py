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
        
        # 等待前端页面渲染
        page.wait_for_timeout(6000)

        print("正在保存页面初始截图...")
        page.screenshot(path="debug_page_1_initial.png", full_page=True)

        log_summary = []

        # ================= 🚀 第一步：处理全屏挂起拦截（大蓝按钮） =================
        suspended_btn = page.locator('button, a').filter(has_text=re.compile(r"Renouveler maintenant|Renew now", re.IGNORECASE))
        
        if suspended_btn.count() > 0 and suspended_btn.first.is_visible():
            print("🚨 状态判定：检测到全屏挂起拦截弹窗！正在点击大蓝按钮...")
            if suspended_btn.first.is_enabled():
                suspended_btn.first.click(timeout=10000)
                log_summary.append("⚠️ 检测到服务被动挂起，已点击大蓝按钮解锁")
                print("大蓝按钮点击成功，等待页面跳转到列表...")
                page.wait_for_timeout(6000)  # 给充足时间让页面刷新到列表页
                page.screenshot(path="debug_page_2_after_blue_click.png", full_page=True)
        else:
            print("🟢 状态判定：未检测到全屏挂起弹窗。")

        # ================= 🚀 第二步：处理列表页面的【Reactivate】黄/橙色按钮 =================
        reactivate_buttons = page.locator('button, a').filter(has_text=re.compile(r"Reactivate", re.IGNORECASE))
        reactivate_count = reactivate_buttons.count()
        clicked_reactivate = 0

        if reactivate_count > 0:
            print(f"⚡ 状态判定：在列表中发现 {reactivate_count} 个需要重新激活的 Reactivate 按钮！")
            for i in range(reactivate_count):
                btn = reactivate_buttons.nth(i)
                if btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=10000)
                    clicked_reactivate += 1
                    print(f"已成功点击第 {i+1} 个 Reactivate 按钮进行激活。")
                    page.wait_for_timeout(6000)  # 激活可能需要后台处理，多等一会儿
            if clicked_reactivate > 0:
                log_summary.append(f"⚡ 成功点击 Reactivate 按钮重新激活服务: {clicked_reactivate} 个")
                page.screenshot(path="debug_page_3_after_reactivate.png", full_page=True)

        # ================= 🚀 第三步：处理常规控制台下的【提前续期】小按钮（最后2小时安全期） =================
        renew_buttons = page.locator("button").filter(has_text=re.compile(r"^(Renew|Renouveler)$", re.IGNORECASE))
        renew_count = renew_buttons.count()
        clicked_renew = 0

        if renew_count > 0:
            print(f"发现 {renew_count} 个常规续期小按钮，正在检查...")
            for i in range(renew_count):
                btn = renew_buttons.nth(i)
                if btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=5000)
                    clicked_renew += 1
                    print(f"已点击第 {i+1} 个常规续期按钮。")
                    page.wait_for_timeout(3000)
            if clicked_renew > 0:
                log_summary.append(f"🔄 常规窗口提前续期成功: {clicked_renew} 个服务")

        # ================= 🚀 第四步：统一检查并点亮【Start 启动】按钮 =================
        start_buttons = page.locator('button[data-variant="start"], button').filter(has_text=re.compile(r"^Start$", re.IGNORECASE))
        start_count = start_buttons.count()
        clicked_start = 0
        skipped_start = 0

        if start_count > 0:
            print(f"正在扫描页面上的所有启动状态（共 {start_count} 个潜在按钮）...")
            for i in range(start_count):
                btn = start_buttons.nth(i)
                if btn.is_visible():
                    if btn.is_enabled():
                        print(f"第 {i+1} 个服务当前处于熄火状态，正在尝试拉起 Start...")
                        btn.click(timeout=10000)
                        clicked_start += 1
                        page.wait_for_timeout(4000)
                    else:
                        skipped_start += 1
                        print(f"第 {i+1} 个服务已在正常运行中（Start按钮变灰不可点），安全跳过。")

        if clicked_start > 0:
            log_summary.append(f"🚀 成功点亮 Start 启动服务: {clicked_start} 个")
        if skipped_start > 0:
            log_summary.append(f"🟢 服务保持在线（无需操作）: {skipped_start} 个")

        # 保存最终执行完的成果截图
        page.screenshot(path="debug_page_4_final.png", full_page=True)

        # ================= 🚀 第五步：组装并发送飞机通知 =================
        if not log_summary:
            status_message = "⚠️ *ACLClouds 自动化任务提醒*\n未检测到任何需要处理的挂起弹窗、激活按钮或到期续期项目，服务均在安全运行中。"
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
        # 无论前面哪个步骤报错或者成功，这里都会雷打不动地给飞机发通知
        if status_message:
            send_telegram_notification(status_message)

with sync_playwright() as playwright:
    run(playwright)
