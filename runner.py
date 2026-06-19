"""
小红书采集 — 后台执行器（供GUI调用）
用法: python runner.py <task_config.json>
"""
import os, sys, json, time, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from 基础模块 import Config, TaskSlot, STEALTH_JS
from 作品采集 import NotesCrawler
from 博主采集 import BloggersCrawler
from 评论采集 import CommentsCrawler


def run(config_path):
    # 彻底替换stdout为UTF-8，解决noconsole下GBK编码崩溃
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tasks_data = data['tasks']
    global_data = data['global']

    cfg = Config()
    cfg.output_base = global_data.get('output_base', cfg.output_base)
    cfg.bio_scroll = global_data.get('bio_scroll', cfg.bio_scroll)
    cfg.checkpoint_enabled = global_data.get('checkpoint_enabled', False)
    cfg.turbo_mode = global_data.get('turbo_mode', False)
    # 网络配置
    cfg.ip_rotate_enabled = global_data.get('ip_rotate_enabled', False)
    cfg.ip_rotate_method = global_data.get('ip_rotate_method', 'pppoe')
    cfg.ip_rotate_frequency = global_data.get('ip_rotate_frequency', 'task')
    cfg.pppoe_name = global_data.get('pppoe_name', '宽带连接')
    cfg.proxy_type = global_data.get('proxy_type', 'http')
    cfg.proxy_host = global_data.get('proxy_host', '')
    cfg.proxy_port = global_data.get('proxy_port', 1080)
    cfg.proxy_username = global_data.get('proxy_username', '')
    cfg.proxy_password = global_data.get('proxy_password', '')

    tasks = []
    for td in tasks_data:
        s = TaskSlot.from_dict(td)
        if s.target:
            tasks.append(s)

    if not tasks:
        print("没有已配置的任务")
        return

    print(f"顺序执行 {len(tasks)} 个任务:")
    for s in tasks:
        print(f"  任务{s.slot_id}: [{s.target}] {s.keyword}")

    # 启动浏览器
    import shutil as _shutil
    edge_paths = [
        _shutil.which("msedge"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    executable_path = None
    for p in edge_paths:
        if p and os.path.exists(p):
            executable_path = p
            break

    ud = cfg.user_data
    os.makedirs(ud, exist_ok=True)
    for name in ['SingletonLock', 'SingletonSocket', 'SingletonCookie', 'lockfile', 'Lockfile']:
        fp = os.path.join(ud, name)
        try:
            if os.path.isfile(fp): os.remove(fp)
            elif os.path.isdir(fp) and name.startswith('Singleton'):
                import shutil; shutil.rmtree(fp, ignore_errors=True)
        except: pass

    pw = sync_playwright().start()
    ua = cfg.ua
    if executable_path:
        ua = ua.replace('Chrome/131.0.0.0', 'Chrome/131.0.0.0 Edg/131.0.0.0')
    vw, vh = random.randint(1260, 1300), random.randint(860, 940)

    context = None
    try:
        ctx_args = dict(
            headless=False, executable_path=executable_path,
            viewport={"width": vw, "height": vh}, user_agent=ua, locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled",
                  "--disable-features=Translate", "--no-first-run", "--no-default-browser-check",
                  "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                  "--enforce-webrtc-ip-permission-check"])
        if cfg.ip_rotate_enabled and cfg.ip_rotate_method == "proxy" and cfg.proxy_host:
            ctx_args["proxy"] = {"server": f"{cfg.proxy_type}://{cfg.proxy_host}:{cfg.proxy_port}"}
            if cfg.proxy_username:
                ctx_args["proxy"]["username"] = cfg.proxy_username
                ctx_args["proxy"]["password"] = cfg.proxy_password
        context = pw.chromium.launch_persistent_context(ud, **ctx_args)
        context.add_init_script(STEALTH_JS)
        context.route("**/search/**", lambda r: r.continue_())
        context.route("**/api/sns/**", lambda r: r.continue_())
        context.route("**/user/profile/**", lambda r: r.abort())

        if os.path.exists(cfg.cookie_file):
            try:
                with open(cfg.cookie_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                if isinstance(cookies, list): context.add_cookies(cookies)
            except: pass

        mp = context.pages[0] if context.pages else context.new_page()
        logged_in = False
        for attempt in range(3):
            mp.goto("https://www.xiaohongshu.com", wait_until="networkidle", timeout=60000)
            mp.wait_for_timeout(2000)
            body = mp.inner_text('body')
            if '登录' not in body[:300] and '登录/注册' not in body[:300]:
                print("[OK] 已登录")
                logged_in = True
                break
            if attempt > 0: print("  刷新二维码...")
            print(f"[!] 请扫码登录 (2分钟)...")
            for _ in range(24):
                mp.wait_for_timeout(5000)
                try:
                    if '登录' not in mp.inner_text('body')[:200]:
                        print("[OK] 登录成功")
                        logged_in = True
                        break
                except: pass
            if logged_in: break
        if not logged_in: print("[!] 登录超时，尝试继续...")
        try: context.storage_state(path=cfg.cookie_file)
        except: pass

        crawlers = {"作品": NotesCrawler, "博主": BloggersCrawler, "评论": CommentsCrawler}
        prev_handler = None

        for i, s in enumerate(tasks):
            print(f"\n{'='*50}")
            print(f">>> 任务{s.slot_id}: [{s.target}] {s.keyword}")
            print(f"{'='*50}")

            # 确保页面存活
            try:
                mp.evaluate("1+1")
            except Exception:
                print("[!] 页面已关闭，创建新页面...")
                mp = context.new_page()
                mp.wait_for_timeout(500)

            if prev_handler:
                try: mp.remove_listener('response', prev_handler)
                except: pass

            c = s.to_config()
            c.output_base = cfg.output_base
            c.bio_scroll = cfg.bio_scroll
            c.checkpoint_enabled = cfg.checkpoint_enabled
            c.turbo_mode = cfg.turbo_mode
            c.cookie_file = cfg.cookie_file
            c.user_data = cfg.user_data

            crawler = crawlers[s.target](c)
            mp.on('response', crawler._handle_search_response)
            prev_handler = crawler._handle_search_response
            try:
                crawler.run_with_page(mp, context)
                print(f"[任务{s.slot_id} {s.target}] 完成")
            except Exception as e:
                print(f"[!] 任务{s.slot_id} 异常: {e}")
                import traceback
                traceback.print_exc()
                try:
                    mp = context.new_page()
                    mp.wait_for_timeout(500)
                except:
                    pass

            # 任务间 IP 轮换
            if cfg.ip_rotate_enabled and cfg.ip_rotate_frequency == "task" and i < len(tasks) - 1:
                from 基础模块 import IpRotator
                IpRotator(cfg).rotate()

            # 任务间穿插轻量浏览（打破规律性）
            if i < len(tasks) - 1:
                try:
                    crawler._casual_browse(mp)
                except Exception:
                    pass

    finally:
        if context:
            try: context.close()
            except: pass
        pw.stop()

    print("\n全部完成!")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python runner.py <task_config.json>")
        sys.exit(1)
    run(sys.argv[1])
