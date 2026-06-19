"""
小红书采集器 v5.5 — GUI客户端
"""
import os, sys, json, time, random, subprocess, threading, queue

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# _loader must import first — it decrypts all modules into sys.modules
from _loader import check_license, get_license_info
from 基础模块 import Config, TaskSlot

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


class TaskPanel:
    TARGETS = ["作品", "博主", "评论"]

    def __init__(self, parent, slot, on_change=None):
        self.slot = slot
        self.on_change = on_change
        self._widgets = {}
        self._frame = tk.LabelFrame(parent, text=slot.one_line(), font=("Microsoft YaHei", 10, "bold"), fg="#333", padx=8, pady=4)
        self._build()

    def _label(self, text):
        return tk.Label(self._frame, text=text, font=("Microsoft YaHei", 9), bg="#fafafa")

    def _entry(self, var, width=8):
        return tk.Entry(self._frame, textvariable=var, font=("Microsoft YaHei", 9), width=width)

    def _combo(self, var, values, width=10):
        return ttk.Combobox(self._frame, textvariable=var, values=values, state="readonly", font=("Microsoft YaHei", 9), width=width)

    def _row(self, widgets, pady=2):
        for w in widgets:
            w.pack(side=tk.LEFT, padx=2, pady=pady)

    def _build(self):
        row1 = [self._label("目标:"),
                self._combo(self._mkvar("target"), self.TARGETS, width=6),
                self._label("关键词:"),
                self._entry(self._mkvar("keyword"), width=10)]
        self._row(row1)
        self._row_dyn = tk.Frame(self._frame, bg="#fafafa")
        self._row_dyn.pack(fill=tk.X, pady=2)
        self._refresh_dyn()

    def _mkvar(self, attr):
        v = tk.StringVar(value=str(getattr(self.slot, attr, "")))
        v.trace_add("write", lambda *a, attr=attr, v=v: self._on_field_change(attr, v))
        self._widgets[attr] = v
        return v

    def _on_field_change(self, attr, var):
        val = var.get()
        if attr in ("likes_min", "fans_min", "comment_likes_min", "max_pages", "max_comment_pages"):
            try: val = int(val)
            except ValueError: val = getattr(self.slot, attr, 0)
        elif attr in ("likes_max", "fans_max", "comment_likes_max"):
            try: val = int(val) if val else None
            except ValueError: val = None
        setattr(self.slot, attr, val)
        self._update_title()
        if self.on_change: self.on_change()

    def _on_target_change(self, *a):
        self.slot.target = self._widgets["target"].get()
        self._rebuild_dyn()
        self._update_title()
        if self.on_change: self.on_change()

    def _rebuild_dyn(self):
        for w in self._row_dyn.winfo_children():
            w.destroy()
        self._refresh_dyn()
        self._widgets["target"].trace_add("write", lambda *a: self._on_target_change())

    def _refresh_dyn(self):
        target = self.slot.target
        wf = self._row_dyn
        if target == "作品":
            tk.Label(wf, text="赞≥", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT, padx=2)
            self._entry(self._mkvar("likes_min"), width=5).pack(side=tk.LEFT, padx=1)
            tk.Label(wf, text="~", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT)
            self._entry(self._mkvar("likes_max"), width=5).pack(side=tk.LEFT, padx=1)
            tk.Label(wf, text="页数:", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT, padx=(8,2))
            self._entry(self._mkvar("max_pages"), width=3).pack(side=tk.LEFT, padx=1)
            tk.Label(wf, text="排序:", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT, padx=(8,2))
            self._combo(self._mkvar("sort_by"), ["综合", "最新", "最多点赞", "最多评论", "最多收藏"], width=8).pack(side=tk.LEFT)
            tk.Label(wf, text="时间:", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT, padx=(8,2))
            self._combo(self._mkvar("publish_time"), ["不限", "一天内", "一周内", "半年内"], width=6).pack(side=tk.LEFT)
        elif target == "博主":
            tk.Label(wf, text="粉丝≥", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT, padx=2)
            self._entry(self._mkvar("fans_min"), width=6).pack(side=tk.LEFT, padx=1)
            tk.Label(wf, text="~", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT)
            self._entry(self._mkvar("fans_max"), width=6).pack(side=tk.LEFT, padx=1)
            tk.Label(wf, text="页数:", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT, padx=(8,2))
            self._entry(self._mkvar("max_pages"), width=3).pack(side=tk.LEFT, padx=1)
        elif target == "评论":
            tk.Label(wf, text="评赞≥", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT, padx=2)
            self._entry(self._mkvar("comment_likes_min"), width=5).pack(side=tk.LEFT, padx=1)
            tk.Label(wf, text="~", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT)
            self._entry(self._mkvar("comment_likes_max"), width=5).pack(side=tk.LEFT, padx=1)
            tk.Label(wf, text="翻页:", font=("Microsoft YaHei", 9), bg="#fafafa").pack(side=tk.LEFT, padx=(8,2))
            self._entry(self._mkvar("max_comment_pages"), width=3).pack(side=tk.LEFT, padx=1)

    def _update_title(self):
        self._frame.config(text=self.slot.one_line())

    def pack(self, **kw):
        self._frame.pack(**kw)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("小红书采集器 v5.5")
        self.root.geometry("1000x750")
        self.root.configure(bg="#fafafa")
        self.tasks = []
        self._proc = None
        self._log_queue = queue.Queue()
        self._load_tasks()
        self._build_ui()

    def _load_tasks(self):
        path = os.path.join(BASE, "tasks.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.tasks = [TaskSlot.from_dict(d) for d in data]
            except:
                pass
        if not self.tasks:
            self.tasks = [TaskSlot(i + 1) for i in range(3)]

    def _save_tasks(self):
        path = os.path.join(BASE, "tasks.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self.tasks], f, ensure_ascii=False, indent=2)

    def _build_ui(self):
        h = tk.Frame(self.root, bg="#ff2442", height=48)
        h.pack(fill=tk.X)
        h.pack_propagate(False)
        tk.Label(h, text=" 小红书采集器 v5.5", font=("Microsoft YaHei", 14, "bold"), fg="white", bg="#ff2442").pack(side=tk.LEFT, padx=15, pady=8)
        tk.Label(h, text="多任务模式 · 作品/博主/评论", font=("Microsoft YaHei", 9), fg="#ffcccc", bg="#ff2442").pack(side=tk.LEFT, pady=12)

        task_frame = tk.Frame(self.root, bg="#fafafa")
        task_frame.pack(fill=tk.X, padx=8, pady=(8, 4))
        self._panels = []
        for i, slot in enumerate(self.tasks):
            panel = TaskPanel(task_frame, slot, on_change=self._save_tasks)
            panel.pack(fill=tk.X, pady=2)
            self._panels.append(panel)

        btn_frame = tk.Frame(self.root, bg="#fafafa")
        btn_frame.pack(fill=tk.X, padx=8, pady=4)
        tk.Button(btn_frame, text="▶ 开始全部任务", font=("Microsoft YaHei", 10, "bold"), bg="#ff2442", fg="white",
                  relief="flat", padx=16, pady=6,
                  command=lambda: threading.Thread(target=self._start_all, daemon=True).start()
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="清空日志", font=("Microsoft YaHei", 9), bg="#95a5a6", fg="white",
                  relief="flat", padx=10, pady=6, command=self._log_clear).pack(side=tk.RIGHT, padx=4)

        cfg_frame = tk.Frame(self.root, bg="#f0f0f0")
        cfg_frame.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(cfg_frame, text="输出目录:", font=("Microsoft YaHei", 9), bg="#f0f0f0").pack(side=tk.LEFT, padx=4)
        self.output_var = tk.StringVar(value=os.path.join(BASE, "output"))
        tk.Entry(cfg_frame, textvariable=self.output_var, font=("Microsoft YaHei", 9), width=40).pack(side=tk.LEFT, padx=2)

        self.log = scrolledtext.ScrolledText(self.root, font=("Consolas", 9), relief="flat", borderwidth=1, bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
        self.log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        self.sb = tk.Label(self.root, text="就绪 | 配置任务后点击「开始全部任务」", font=("Microsoft YaHei", 9), bg="#34495e", fg="white", anchor="w", padx=10, pady=4)
        self.sb.pack(fill=tk.X)

        self.root.after(100, self._poll_log)

    def _log(self, text):
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def _log_append(self, text):
        self._log_queue.put(text)

    def _log_clear(self):
        self.log.delete("1.0", tk.END)

    def _poll_log(self):
        while not self._log_queue.empty():
            self._log(self._log_queue.get())
        self.root.after(200, self._poll_log)

    def _start_all(self):
        self._save_tasks()
        done_tasks = [s for s in self.tasks if s.target]
        if not done_tasks:
            self._log_append("没有已配置的任务\n")
            return

        config = {
            "tasks": [s.to_dict() for s in done_tasks],
            "global": {
                "output_base": self.output_var.get(),
                "checkpoint_enabled": False,
                "turbo_mode": False,
            }
        }

        cfg_path = os.path.join(BASE, "_run_config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        self.sb.config(text=f"执行中... {len(done_tasks)}个任务")
        self._log_append(f"\n{'='*50}\n")
        self._log_append(f"开始执行 {len(done_tasks)} 个任务\n")
        for s in done_tasks:
            self._log_append(f"  {s.one_line()}\n")
        self._log_append(f"{'='*50}\n\n")

        try:
            cmd = [sys.executable, "--run", cfg_path]
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1, cwd=BASE
            )
            for line in self._proc.stdout:
                self._log_append(line)
            self._proc.wait()
            self._log_append(f"\n{'='*50}\n")
            self._log_append(f"全部完成 (exit code: {self._proc.returncode})\n")
            self.sb.config(text=f"完成! {len(done_tasks)}个任务已执行")
        except Exception as e:
            self._log_append(f"执行失败: {e}\n")
            self.sb.config(text=f"失败: {e}")
        finally:
            self._proc = None
            try: os.remove(cfg_path)
            except: pass

    def run(self):
        self.root.mainloop()


def run_headless(config_path):
    """Headless mode: called via --run <config>"""
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except: pass

    # _loader must be imported first to decrypt modules
    import _loader
    from runner import run
    run(config_path)


def main():
    # --run mode for subprocess execution within EXE
    if "--run" in sys.argv:
        idx = sys.argv.index("--run")
        if idx + 1 < len(sys.argv):
            run_headless(sys.argv[idx + 1])
            return

    valid, msg = check_license()
    info = get_license_info()

    if not valid:
        root = tk.Tk()
        root.withdraw()
        contact = ("\n\n如需获取正式版，请联系：\n微信：gongjumao123\n"
                   "淘宝：猫猫嘴无敌工作室\ngongjumaotianxiawudi.taobao.com")
        messagebox.showerror("许可证无效", msg + contact)
        root.destroy()
        return

    App().run()


if __name__ == "__main__":
    main()
