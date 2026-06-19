"""XHS Collector v5.0 — Content Collector"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import os, sys, json, threading, time, re

class XHSCollectorApp:
    def __init__(self):
        self.root = tk.Tk(); self.root.title("XHS Collector v5.0"); self.root.geometry("950x700")
        self.data = []; self.running = False; self._build_ui()

    def _build_ui(self):
        h = tk.Frame(self.root, bg="#ff2442", height=50); h.pack(fill=tk.X); h.pack_propagate(False)
        tk.Label(h, text=" XHS Collector v5.0 — 小红书内容采集", font=("Microsoft YaHei", 14, "bold"), fg="white", bg="#ff2442").pack(side=tk.LEFT, padx=15, pady=8)

        ctrl = tk.Frame(self.root, bg="#f5f6fa"); ctrl.pack(fill=tk.X, padx=8, pady=8)
        tk.Label(ctrl, text="关键词:", font=("Microsoft YaHei", 10), bg="#f5f6fa").pack(side=tk.LEFT)
        self.kw_var = tk.StringVar(); tk.Entry(ctrl, textvariable=self.kw_var, font=("Microsoft YaHei", 10), width=12).pack(side=tk.LEFT, ipady=2, padx=3)
        tk.Label(ctrl, text="数量:", font=("Microsoft YaHei", 10), bg="#f5f6fa").pack(side=tk.LEFT, padx=(8, 2))
        self.count_var = tk.StringVar(value="20"); tk.Entry(ctrl, textvariable=self.count_var, font=("Microsoft YaHei", 10), width=5).pack(side=tk.LEFT, ipady=2)
        tk.Label(ctrl, text="排序:", font=("Microsoft YaHei", 10), bg="#f5f6fa").pack(side=tk.LEFT, padx=(8, 2))
        self.sort_var = tk.StringVar(value="综合")
        for s in ["综合", "最新", "最热"]: tk.Radiobutton(ctrl, text=s, variable=self.sort_var, value=s, font=("Microsoft YaHei", 9), bg="#f5f6fa").pack(side=tk.LEFT)

        tk.Button(ctrl, text="▶ 开始采集", font=("Microsoft YaHei", 10, "bold"), bg="#ff2442", fg="white", relief="flat", padx=18, pady=5, command=lambda: threading.Thread(target=self._collect, daemon=True).start()).pack(side=tk.LEFT, padx=15)
        tk.Button(ctrl, text="暂停", font=("Microsoft YaHei", 9), bg="#e67e22", fg="white", relief="flat", padx=10, pady=5, command=self._pause).pack(side=tk.LEFT, padx=3)
        tk.Button(ctrl, text="导出JSON", font=("Microsoft YaHei", 9), bg="#2980b9", fg="white", relief="flat", padx=12, pady=5, command=self._export).pack(side=tk.LEFT, padx=3)
        tk.Button(ctrl, text="导出CSV", font=("Microsoft YaHei", 9), bg="#27ae60", fg="white", relief="flat", padx=12, pady=5, command=lambda: self._export_csv()).pack(side=tk.LEFT, padx=3)
        tk.Button(ctrl, text="清空", font=("Microsoft YaHei", 9), bg="#95a5a6", fg="white", relief="flat", padx=10, pady=5, command=self._clear).pack(side=tk.RIGHT, padx=3)

        main = tk.Frame(self.root); main.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.result = scrolledtext.ScrolledText(main, font=("Microsoft YaHei", 10), relief="flat", borderwidth=1, padx=10, pady=10)
        self.result.pack(fill=tk.BOTH, expand=True)

        self.sb = tk.Label(self.root, text="就绪 | 需Playwright + 小红书Cookie | 输入关键词开始", font=("Microsoft YaHei", 9), bg="#34495e", fg="white", anchor="w", padx=10, pady=4)
        self.sb.pack(fill=tk.X)

    def _pause(self): self.running = False; self.sb.config(text="已暂停")

    def _clear(self): self.data.clear(); self.result.delete("1.0", tk.END); self.sb.config(text="已清空")

    def _collect(self):
        kw = self.kw_var.get().strip()
        if not kw:
            self.result.insert(tk.END, "请先输入关键词\n")
            return
        count = int(self.count_var.get()) if self.count_var.get().isdigit() else 20
        self.running = True; self.data = []
        self.result.delete("1.0", tk.END)
        self.result.insert(tk.END, f"开始采集: '{kw}' (目标{count}条)\n\n")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.result.insert(tk.END, "需要安装Playwright:\n")
            self.result.insert(tk.END, "1. pip install playwright\n")
            self.result.insert(tk.END, "2. playwright install chromium\n\n")
            self.result.insert(tk.END, "安装完成后请先登录小红书获取Cookie:\n")
            self.result.insert(tk.END, "手动操作步骤:\n")
            self.result.insert(tk.END, "  1) 运行 playwright codegen xiaohongshu.com\n")
            self.result.insert(tk.END, "  2) 扫码登录小红书\n")
            self.result.insert(tk.END, "  3) 复制浏览器Cookie到程序配置\n")
            self.sb.config(text="Playwright未安装"); return

        cookies_path = os.path.join(os.path.expanduser("~"), ".xhs_cookies.json")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )

                # Load saved cookies
                if os.path.exists(cookies_path):
                    with open(cookies_path, "r") as f: cookies = json.load(f)
                    context.add_cookies(cookies)
                    self.result.insert(tk.END, "已加载保存的登录Cookie\n")

                page = context.new_page()

                # Stealth injection
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});
                    window.chrome = {runtime: {}};
                """)

                search_url = f"https://www.xiaohongshu.com/search_result?keyword={kw}&sort=general"
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)

                # Wait for login if needed
                if "login" in page.url:
                    self.result.insert(tk.END, "需要登录小红书，请在浏览器中扫码登录...\n")
                    self.sb.config(text="等待扫码登录 (90秒超时)...")
                    try:
                        page.wait_for_url("**/search_result**", timeout=90000)
                        self.result.insert(tk.END, "登录成功!\n")
                        cookies = context.cookies()
                        with open(cookies_path, "w") as f: json.dump(cookies, f)
                        self.result.insert(tk.END, "Cookie已保存\n")
                    except:
                        self.result.insert(tk.END, "登录超时，请重试\n")
                        browser.close(); return

                # Scroll to load content
                self.result.insert(tk.END, "正在加载内容...\n")
                for i in range(min(count // 5 + 1, 15)):
                    if not self.running: break
                    page.evaluate("window.scrollBy(0, 800)")
                    time.sleep(1.5)
                    self.sb.config(text=f"滚动加载... {i+1}")
                    self.root.update()

                # Extract posts
                items = page.query_selector_all(".note-item, .feeds-page .note-item, section.note-item, [class*='note']")
                self.result.insert(tk.END, f"发现 {len(items)} 条笔记，正在提取...\n\n")

                for i, item in enumerate(items[:count]):
                    if not self.running: break
                    try:
                        title_el = item.query_selector(".title, .note-title, [class*='title']")
                        title = title_el.inner_text() if title_el else "无标题"

                        author_el = item.query_selector(".author, .name, [class*='author'], [class*='name']")
                        author = author_el.inner_text() if author_el else "未知"

                        like_el = item.query_selector(".like-count, .count, [class*='like']")
                        likes_text = like_el.inner_text() if like_el else "0"
                        likes = int(re.sub(r'\D', '', likes_text)) if re.sub(r'\D', '', likes_text) else 0

                        link_el = item.query_selector("a[href*='explore']")
                        url = "https://www.xiaohongshu.com" + link_el.get_attribute("href") if link_el else ""

                        post = {"title": title.strip(), "author": author.strip(), "likes": likes, "url": url}
                        self.data.append(post)
                        self.result.insert(tk.END, f"  [{i+1}] {title[:40]} | {author} | {likes}赞\n")
                        self.sb.config(text=f"采集: {i+1}/{count}")
                        self.root.update()
                    except Exception as e:
                        pass

                # If selectors failed, try API interception approach
                if len(self.data) == 0:
                    self.result.insert(tk.END, "\n直接DOM提取未命中，尝试API拦截模式...\n")
                    captured = []

                    def handle_response(response):
                        if "/api/sns/web/v1/search/notes" in response.url and response.status == 200:
                            try:
                                resp_data = response.json()
                                items_data = resp_data.get("data", {}).get("items", [])
                                for item in items_data:
                                    note = item.get("note_card", item)
                                    captured.append({
                                        "title": note.get("display_title", ""),
                                        "author": note.get("user", {}).get("nickname", ""),
                                        "likes": note.get("interact_info", {}).get("liked_count", 0),
                                        "url": f"https://www.xiaohongshu.com/explore/{note.get('note_id', '')}"
                                    })
                            except: pass

                    page.on("response", handle_response)
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(8)

                    for i in range(5):
                        if not self.running: break
                        page.evaluate("window.scrollBy(0, 1000)")
                        time.sleep(2)

                    self.data = captured[:count]
                    for i, post in enumerate(self.data):
                        self.result.insert(tk.END, f"  [{i+1}] {post['title'][:40]} | {post['author']} | {post['likes']}赞\n")

                browser.close()
        except Exception as e:
            self.result.insert(tk.END, f"\n错误: {e}\n")
            self.result.insert(tk.END, "提示: 确保已安装chromium: playwright install chromium\n")
            self.sb.config(text=f"采集出错: {e}")

        self.result.insert(tk.END, f"\n=== 采集完成 ===\n共 {len(self.data)} 条\n")
        self.sb.config(text=f"完成! 采集 {len(self.data)} 条 | 关键词: {kw}")

    def _export(self):
        if not self.data: return
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if p:
            with open(p, "w", encoding="utf-8") as f: json.dump(self.data, f, ensure_ascii=False, indent=2)
            self.sb.config(text=f"已导出 {p}"); messagebox.showinfo("导出", f"已导出 {len(self.data)} 条")

    def _export_csv(self):
        if not self.data: return
        import csv
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p:
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["title", "author", "likes", "url"])
                w.writeheader(); w.writerows(self.data)
            self.sb.config(text=f"已导出 {p}"); messagebox.showinfo("导出", f"已导出 {len(self.data)} 条CSV")

    def run(self): self.root.mainloop()

if __name__ == "__main__": XHSCollectorApp().run()
App = XHSCollectorApp
