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
        print("正在访问项目列表页...")
        page.goto("https://dash.aclclouds.com/projects", timeout=60000)
        page.wait_for_timeout(5000) 

        print("保存列表页初始截图...")
        page.screenshot(path="debug_1_projects_list.png", full_page=True)

        log_summary = []

        # ================= 阶段 1：异常拦截大蓝按钮处理 =================
        suspended_btn = page.locator('button, a').filter(has_text=re.compile(r"Renouveler maintenant|Renew now", re.IGNORECASE))
        if suspended_btn.count() > 0 and suspended_btn.first.is_visible():
            print("🚨 状态判定：检测到全屏挂起拦截弹窗！正在点击大蓝按钮...")
            if suspended_btn.first.is_enabled():
                suspended_btn.first.click(timeout=10000)
                log_summary.append("⚠️ 检测到服务被动挂起，已点击大蓝按钮解锁")
                page.wait_for_timeout(6000) 
                page.screenshot(path="debug_2_after_blue_button.png", full_page=True)

        # ================= 阶段 2：处理列表页面的【Reactivate】激活按钮 =================
        reactivate_buttons = page.locator('button, a').filter(has_text=re.compile(r"Reactivate", re.IGNORECASE))
        if reactivate_buttons.count() > 0:
            print(f"⚡ 状态判定：发现需要激活的 Reactivate 按钮！")
            for i in range(reactivate_buttons.count()):
                btn = reactivate_buttons.nth(i)
                if btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=10000)
                    log_summary.append("⚡ 成功点击 Reactivate 按钮重新激活服务")
                    page.wait_for_timeout(6000) 
            page.screenshot(path="debug_3_after_reactivate.png", full_page=True)

        # ================= 阶段 3：常规列表页续期检查 =================
        renew_list_buttons = page.locator("button").filter(has_text=re.compile(r"^(Renew|Renouveler)$", re.IGNORECASE))
        if renew_list_buttons.count() > 0:
            for i in range(renew_list_buttons.count()):
                btn = renew_list_buttons.nth(i)
                if btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=5000)
                    log_summary.append("🔄 列表页常规窗口提前续期成功")
                    page.wait_for_timeout(3000)

        # ================= 阶段 4：点击 Manage 进入控制台 =================
        manage_buttons = page.locator('button, a').filter(has_text=re.compile(r"Manage", re.IGNORECASE))
        if manage_buttons.count() > 0 and manage_buttons.first.is_visible():
            print("🔍 正在点击 Manage 按钮...")
            old_pages_count = len(context.pages)
            manage_buttons.first.click(timeout=10000)
            page.wait_for_timeout(3000) 
            
            if len(context.pages) > old_pages_count:
                print("💡 检测到平台打开了新标签页，切换控制权...")
                page = context.pages[-1]
            else:
                print("💡 平台未开新页，单页应用原地路由切换。")

            # ================= 阶段 5：智能死等并精准点击 Start 按钮 =================
            start_button_locator = page.locator('button, a').filter(has_text=re.compile(r"Start", re.IGNORECASE)).first
            
            # 1. 严格隔离等待逻辑
            try:
                print("⏳ [关键步骤] 正在高频检索并等待 Start 按钮渲染到屏幕上...")
                start_button_locator.wait_for(state="visible", timeout=25000)
                print("🎯 [成功] 终于在控制台页面抓到了动态渲染出来的 Start 按钮！")
            except Exception as wait_err:
                print("❌ 智能等待超时，在规定时间内页面未渲染出 Start 按钮。")
                page.screenshot(path="debug_error_timeout.png", full_page=True)
                log_summary.append("❌ 错误：在控制台页面没等到 Start 按钮出现")
                raise wait_err

            # 2. 截图存档加载完的控制台状态
            page.screenshot(path="debug_4_console_loaded.png", full_page=True)

            # 3. 严格执行单次安全点击
            if start_button_locator.is_enabled():
                print("🚀 确认服务器当前处于 Offline 熄火状态，正在下发点击拉起...")
                try:
                    # 优先常规点击
                    start_button_locator.click(timeout=10000)
                    print("第一次常规点击已成功送达，等待 8 秒让平台响应...")
                    page.wait_for_timeout(8000)
                    log_summary.append("🚀 核心保活成功：已成功下发 Start 启动指令！")
                except Exception as click_err:
                    print(f"⚠️ 常规点击被拦截，正在切换至 JS 底层驱动进行强力点击: {click_err}")
                    try:
                        start_button_locator.evaluate("node => node.click()")
                        page.wait_for_timeout(8000)
                        log_summary.append("🚀 核心保活成功：已通过 JS 底层强行激活 Start 启动！")
                    except Exception as js_err:
                        print(f"❌ 强行点击也失败: {js_err}")
                        log_summary.append(f"❌ 错误：点击 Start 按钮失败 ({js_err})")
            else:
                print("🟢 Start 按钮当前处于禁用状态（变灰），说明服务器本身已经是开启运行状态。")
                log_summary.append("🟢 服务器已在运行中（无需操作）")
        else:
            print("❌ 没在项目列表页找到可见的 Manage 按钮！")
            log_summary.append("❌ 错误：未找到 Manage 按钮")

        # 最终成果截图
        page.screenshot(path="debug_5_final.png", full_page=True)

        # ================= 阶段 6：组装结算通知 =================
        if not log_summary:
            status_message = "⚠️ *ACLClouds 自动化任务提醒*\n未检测到任何需要处理的异常，服务均在安全运行中。"
        else:
            status_message = "✅ *ACLClouds 自动化闭环运行完毕*\n" + "\n".join(log_summary)

        print("整个复合自动化任务顺利结束。")

    except Exception as e:
        # 如果是已知处理过的等待报错，不再重复覆盖大日志
        if "在控制台页面没等到 Start 按钮出现" in str(log_summary):
            status_message = "❌ *ACLClouds 自动续期运行失败*\n错误原因: `未等到 Start 按钮出现`"
        else:
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
