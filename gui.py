"""
B站视频下载器 - GUI 界面 (tkinter)
功能:
  - 单个/批量链接输入
  - 清晰度选择 (best / 1080 / 720 / 480 / 360)
  - 下载模式 (视频+音频 / 仅视频 / 仅音频 / 封面)
  - 下载队列 (并发 1，可扩展)
  - 实时进度 / 速度 / 剩余时间
  - 登录态: cookies.txt 文件，或下拉框选择本机已安装的浏览器
  - 自动探测 ffmpeg
"""
import os
import sys
import re
import threading
import queue
import time
from pathlib import Path
from typing import Optional

if getattr(sys, 'frozen', False):
    _MEIPASS = sys._MEIPASS
    if _MEIPASS:
        sys.path.insert(0, _MEIPASS)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import downloader as core
import updater
import cookies_tool


APP_TITLE = f"B站 / 小红书 / 抖音 / 微博 / 西瓜 / AcFun 视频下载器 v{updater.APP_VERSION}"
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "video")
Path(DEFAULT_DIR).mkdir(parents=True, exist_ok=True)

FALLBACK_BROWSERS = ["chrome", "edge", "firefox", "brave", "opera", "chromium"]


def browser_choices() -> list:
    names = ["(不使用)"]
    try:
        for item in cookies_tool.available_browsers():
            display = item[0] if isinstance(item, (list, tuple)) and item else str(item)
            if display and display not in names:
                names.append(display)
    except Exception:
        pass
    for name in FALLBACK_BROWSERS:
        if name not in names:
            names.append(name)
    return names


# 进度信息跨线程传递
class ProgressEvent:
    __slots__ = ("status", "percent", "speed", "eta", "filename", "title", "error")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


class DownloaderGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x640")
        self.root.minsize(820, 560)

        # 状态
        self.queue: "queue.Queue[ProgressEvent]" = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_flag = threading.Event()
        self.current_event: Optional[ProgressEvent] = None
        self.poll_id = None

        self._build_ui()
        self._poll_queue()
        self.root.after(1500, self._auto_check_update)

    # ---------------- UI ----------------
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("TLabel", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 9))
        style.configure("Header.TLabel", font=("Microsoft YaHei UI", 11, "bold"))

        pad = {"padx": 6, "pady": 4}

        # 顶部:输入区
        top = ttk.LabelFrame(self.root, text="视频链接", padding=8)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="链接 (可多个,空格/换行分隔):").pack(anchor="w")
        self.url_text = tk.Text(top, height=4, font=("Consolas", 10))
        self.url_text.pack(fill="x", pady=(4, 4))
        ttk.Label(
            top,
            text="支持: B站 ( BV号 / av号 / ep号 / b23.tv短链 )   小红书 ( xiaohongshu.com / xhslink.com )   抖音 ( douyin.com/video 、 douyin.com/share/video 、 v.douyin.com短链 )   微博 ( weibo.com / weibo.cn / video.weibo.com )   西瓜视频 ( ixigua.com )   AcFun ( acfun.cn )",
            foreground="#666",
            wraplength=860,
            justify="left",
        ).pack(anchor="w")

        # 选项行
        opts = ttk.Frame(top)
        opts.pack(fill="x", pady=4)

        ttk.Label(opts, text="清晰度:").pack(side="left")
        self.quality_var = tk.StringVar(value="1080")
        ttk.Combobox(
            opts, textvariable=self.quality_var, width=10, state="readonly",
            values=["best", "2160", "1080", "720", "480", "360", "240"],
        ).pack(side="left", padx=(4, 12))

        ttk.Label(opts, text="下载内容:").pack(side="left")
        self.mode_var = tk.StringVar(value="视频+音频")
        ttk.Combobox(
            opts, textvariable=self.mode_var, width=12, state="readonly",
            values=["视频+音频", "仅视频", "仅音频", "封面"],
        ).pack(side="left", padx=(4, 12))

        ttk.Label(opts, text="保存目录:").pack(side="left")
        self.dir_var = tk.StringVar(value=DEFAULT_DIR)
        ttk.Entry(opts, textvariable=self.dir_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(opts, text="浏览…", command=self._pick_dir).pack(side="left")

        # 登录态
        login = ttk.LabelFrame(self.root, text="cookies (抖音必填 / B站高清·会员需要)", padding=8)
        login.pack(fill="x", **pad)

        ttk.Label(login, text="cookies.txt:").grid(row=0, column=0, sticky="w")
        self.cookie_var = tk.StringVar()
        ttk.Entry(login, textvariable=self.cookie_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(login, text="选择…", command=self._pick_cookie).grid(row=0, column=2)
        ttk.Button(login, text="自动获取Cookies", command=self._on_auto_cookies).grid(row=0, column=3, padx=(6, 0))

        ttk.Label(login, text="或从浏览器:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.browser_var = tk.StringVar(value="(不使用)")
        ttk.Combobox(
            login, textvariable=self.browser_var, width=28, state="readonly",
            values=browser_choices(),
        ).grid(row=1, column=1, sticky="w", padx=4, pady=(6, 0))

        ttk.Label(login, text="提示: 点“自动获取Cookies”可从已登录的浏览器直接读取; 抖音需先在浏览器访问一次 douyin.com 并通过验证码",
                  foreground="#666").grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        login.columnconfigure(1, weight=1)

        # 操作按钮
        btn_bar = ttk.Frame(self.root)
        btn_bar.pack(fill="x", **pad)
        self.parse_btn = ttk.Button(btn_bar, text="解析信息", command=self._on_parse)
        self.parse_btn.pack(side="left")
        self.start_btn = ttk.Button(btn_bar, text="开始下载", command=self._on_start)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(btn_bar, text="停止", command=self._on_stop, state="disabled")
        self.stop_btn.pack(side="left")
        ttk.Button(btn_bar, text="使用说明", command=self._show_help).pack(side="right", padx=(4, 0))
        ttk.Button(btn_bar, text="检查更新", command=self._on_check_update).pack(side="right", padx=4)
        ttk.Button(btn_bar, text="更新设置", command=self._on_update_settings).pack(side="right", padx=4)
        ttk.Button(btn_bar, text="清空日志", command=self._clear_log).pack(side="right", padx=4)
        ttk.Button(btn_bar, text="打开目录", command=self._open_dir).pack(side="right", padx=4)

        # 信息区: 当前视频 + 进度
        info = ttk.LabelFrame(self.root, text="当前任务", padding=8)
        info.pack(fill="x", **pad)

        self.title_var = tk.StringVar(value="—")
        ttk.Label(info, textvariable=self.title_var, style="Header.TLabel").pack(anchor="w")
        self.detail_var = tk.StringVar(value="等待开始")
        ttk.Label(info, textvariable=self.detail_var, foreground="#444").pack(anchor="w", pady=(2, 6))

        self.progress = ttk.Progressbar(info, mode="determinate", maximum=100)
        self.progress.pack(fill="x")

        # 日志
        log_frame = ttk.LabelFrame(self.root, text="日志", padding=8)
        log_frame.pack(fill="both", expand=True, **pad)
        self.log = scrolledtext.ScrolledText(log_frame, height=14, font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief="sunken").pack(fill="x", side="bottom")

    # ---------------- Actions ----------------
    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get() or DEFAULT_DIR)
        if d:
            self.dir_var.set(d)

    def _pick_cookie(self):
        f = filedialog.askopenfilename(
            title="选择 cookies.txt",
            filetypes=[("Netscape cookies", "*.txt"), ("全部", "*.*")],
        )
        if f:
            self.cookie_var.set(f)

    def _platforms_from_input(self) -> list[str]:
        urls = self._parse_urls()
        found: list[str] = []
        for u in urls:
            p = core.detect_platform(u)
            if p in cookies_tool.PLATFORM_DOMAINS and p not in found:
                found.append(p)
        return found or list(cookies_tool.PLATFORM_DOMAINS.keys())

    def _auto_cookies(self, platforms: list[str]):
        result = cookies_tool.auto_get_cookies(platforms)
        return result

    def _on_auto_cookies(self):
        platforms = self._platforms_from_input()
        names = "、".join(cookies_tool.PLATFORM_NAMES.get(p, p) for p in platforms)
        self.status_var.set(f"正在自动获取 {names} cookies…")
        self._log(f"自动获取 cookies ({names}) …")

        def task():
            try:
                result = self._auto_cookies(platforms)
            except Exception as exc:
                self.root.after(0, lambda: (self.status_var.set("获取 cookies 失败"), messagebox.showerror("自动获取失败", str(exc))))
                return
            self.root.after(0, lambda: self._apply_auto_cookies(result, platforms))

        threading.Thread(target=task, daemon=True).start()

    def _apply_auto_cookies(self, result: dict, platforms: list[str]):
        total = result.get("total", 0)
        found = result.get("found", [])
        missing = result.get("missing", [])
        path = result.get("path")
        details = result.get("details", []) or []
        if path:
            self.cookie_var.set(path)
            self._log(f"  已获取 {total} 条 cookies -> {path}")
        scanned = []
        for browser, status, count in details:
            scanned.append(browser)
            self._log(f"  {browser}: {status} ({count})")
        if scanned:
            self._log(f"  本次共扫描 {len(scanned)} 个浏览器: {'、'.join(scanned)}")
        if found:
            names = "、".join(cookies_tool.PLATFORM_NAMES.get(p, p) for p in found)
            self.status_var.set(f"已获取 {names} cookies")
        if missing:
            names = "、".join(cookies_tool.PLATFORM_NAMES.get(p, p) for p in missing)
            self.status_var.set(f"{names} 未找到 cookies")
            usable = [b for b, status, count in details if count and "不可用" not in str(status)]
            tip = f"已扫描的浏览器: {'、'.join(scanned) if scanned else '无'}\n\n"
            if usable:
                tip += f"其中 {usable[0]} 能正常读取，可以换这个浏览器再试一次。\n\n"
            answer = messagebox.askyesno(
                "需要先访问网站",
                f"没有从浏览器里找到 {names} 的 cookies。\n\n"
                f"{tip}"
                f"请在浏览器里打开 {names} 并正常浏览（抖音需通过验证码），\n"
                "然后再点一次“自动获取Cookies”。\n\n"
                "现在帮你打开网站吗？",
            )
            if answer:
                cookies_tool.open_platform_sites(missing)
        elif not path:
            messagebox.showwarning("未获取到", "当前所有支持的平台都没有找到 cookies。")

    def _open_dir(self):
        d = self.dir_var.get()
        if d and os.path.isdir(d):
            try:
                if os.name == "nt":
                    os.startfile(d)  # type: ignore[attr-defined]
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", d])
            except Exception as e:
                messagebox.showerror("打开失败", str(e))
        else:
            messagebox.showwarning("提示", "目录不存在")

    def _parse_urls(self) -> list[str]:
        raw = self.url_text.get("1.0", "end").strip()
        if not raw:
            return []
        # 空格/换行/逗号/分号
        parts = re.split(r"[\s,;]+", raw)
        return [p for p in parts if p]

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _on_parse(self):
        urls = self._parse_urls()
        if not urls:
            messagebox.showinfo("提示", "请先填写链接")
            return
        u = urls[0]
        self._log(f"解析: {u}")
        self.status_var.set("正在解析…")

        def task():
            try:
                info = core.probe(
                    u,
                    cookie_file=self.cookie_var.get().strip() or None,
                    cookies_from_browser=None if self.browser_var.get() == "(不使用)" else self.browser_var.get(),
                )
                title = info.get("title", "(无标题)")
                uploader = info.get("uploader") or info.get("channel") or ""
                duration = info.get("duration") or 0
                self.queue.put(ProgressEvent(
                    status="parsed",
                    title=f"标题: {title}",
                    filename=f"UP: {uploader}    时长: {duration//60}分{duration%60}秒",
                ))
            except Exception as e:
                self.queue.put(ProgressEvent(status="error", error=f"解析失败: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def _on_start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提示", "已有任务在进行中")
            return
        urls = self._parse_urls()
        if not urls:
            messagebox.showinfo("提示", "请先填写链接")
            return
        save_dir = self.dir_var.get().strip() or DEFAULT_DIR
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        quality = self.quality_var.get()
        mode_text = self.mode_var.get()
        mode_map = {
            "视频+音频": "video",
            "仅视频": "video",
            "仅音频": "audio",
            "封面": "cover",
        }
        download_mode = mode_map.get(mode_text, "video")
        # 仅视频也按 video 模式走(取 bestvideo*+bestaudio 会自动合并),目前简化为 video
        cookie_file = self.cookie_var.get().strip() or None
        cb = None if self.browser_var.get() == "(不使用)" else self.browser_var.get()

        self.stop_flag.clear()
        self.start_btn.configure(state="disabled")
        self.parse_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress["value"] = 0
        self.status_var.set(f"共 {len(urls)} 个任务")

        def task():
            ok = 0
            run_cookie = cookie_file
            if not run_cookie and not cb and any(
                core.detect_platform(u) == "douyin" for u in urls
            ):
                self._log("抖音需要 cookies, 正在自动从浏览器获取…")
                try:
                    result = cookies_tool.auto_get_cookies(["douyin"])
                    if result.get("path"):
                        run_cookie = result["path"]
                        self._log(f"  自动获取到 {result.get('total')} 条 cookies")
                    else:
                        self._log("  浏览器里没有抖音 cookies, 请先访问一次 douyin.com")
                except Exception as exc:
                    self._log(f"  自动获取 cookies 失败: {exc}")
            if not self.stop_flag.is_set():
                self._prepare_ffmpeg()
            for i, u in enumerate(urls, 1):
                if self.stop_flag.is_set():
                    self._log("已停止")
                    break
                self._log(f"[{i}/{len(urls)}] 开始: {u}")
                self.queue.put(ProgressEvent(status="task_start", title=f"[{i}/{len(urls)}] {u}", filename=""))
                try:
                    info = core.download(
                        url=u,
                        save_dir=save_dir,
                        quality=quality,
                        download_mode=download_mode,
                        cookie_file=run_cookie,
                        cookies_from_browser=cb,
                        progress_hook=self._make_hook(i, len(urls)),
                    )
                    fn = info.get("_filename") or info.get("title", "")
                    self._log(f"  完成 -> {fn}")
                    ok += 1
                except Exception as e:
                    self._log(f"  失败: {e}")
                    self.queue.put(ProgressEvent(status="error", error=str(e)))
            self.queue.put(ProgressEvent(status="all_done", filename=f"完成 {ok}/{len(urls)}"))

        self.worker_thread = threading.Thread(target=task, daemon=True)
        self.worker_thread.start()

    def _on_stop(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.stop_flag.set()
            self._log("请求停止…")
            self.stop_btn.configure(state="disabled")

    def _on_update_settings(self):
        current = updater.load_config()["repository"]
        value = messagebox.askstring(
            "更新设置",
            "请输入 GitHub 仓库，格式：用户名/仓库名\n例如：your-name/bilibili-downloader",
            initialvalue=current,
        )
        if value is None:
            return
        repository = value.strip().strip("/")
        if repository and repository.count("/") != 1:
            messagebox.showerror("格式错误", "仓库格式应为：用户名/仓库名")
            return
        updater.save_repository(repository)
        messagebox.showinfo("已保存", "更新地址已保存。")

    def _check_update_result(self, result):
        if result is None:
            self.status_var.set("未发现新版本")
            messagebox.showinfo("检查更新", "当前已经是最新版本。")
            return
        if messagebox.askyesno(
            "发现新版本",
            f"发现新版本 {result['tag']}，是否下载并安装？\n下载完成后程序会自动重启。",
        ):
            self._download_update(result)
        else:
            self.status_var.set("已取消更新")

    def _download_update(self, result):
        progress = tk.Toplevel(self.root)
        progress.title("下载更新")
        progress.geometry("360x130")
        progress.resizable(False, False)
        progress.transient(self.root)
        progress.grab_set()
        ttk.Label(progress, text=f"正在下载 {result['tag']}").pack(anchor="w", padx=16, pady=(16, 8))
        bar = ttk.Progressbar(progress, mode="determinate", maximum=100)
        bar.pack(fill="x", padx=16)
        label = ttk.Label(progress, text="0%")
        label.pack(anchor="e", padx=16, pady=5)

        def worker():
            try:
                def report(received, total):
                    percent = received / total * 100 if total else 0
                    self.root.after(0, lambda: (bar.configure(value=percent), label.configure(text=f"{percent:.0f}%")))
                updater.install_update(result, report)
                self.root.after(0, lambda: (progress.destroy(), self.root.destroy()))
            except Exception as exc:
                self.root.after(0, lambda: (progress.destroy(), messagebox.showerror("更新失败", str(exc))))

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_update(self):
        repository = updater.load_config()["repository"]
        if not repository:
            self._on_update_settings()
            repository = updater.load_config()["repository"]
            if not repository:
                return
        self.status_var.set("正在检查更新…")

        def worker():
            try:
                result = updater.check_update(repository)
                self.root.after(0, lambda: self._check_update_result(result))
            except Exception as exc:
                self.root.after(0, lambda: (self.status_var.set("检查更新失败"), messagebox.showerror("检查更新失败", str(exc))))

        threading.Thread(target=worker, daemon=True).start()

    def _auto_check_update(self):
        if updater.load_config()["repository"]:
            self._on_check_update()

    def _show_help(self):
        text = """\
第一步：找到视频链接
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【电脑端】复制网址
1. 打开 B站 / 小红书 / 抖音 / 微博 / 西瓜视频 / AcFun，找到想下载的视频
2. 看浏览器顶部那条地址栏（显示网址的地方）
3. 点击地址栏，按 Ctrl+A 全选，再按 Ctrl+C 复制

【手机端】复制链接
1. 在 B站 / 小红书 / 抖音 / 微博 / 西瓜视频 / AcFun App 里找到视频
2. 点击"分享"按钮（右下角箭头图标）
3. 点击"复制链接"
   注意：小红书必须用这种方式复制，网页地址栏里的短地址缺参数会解析失败。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
支持的链接格式：
  B站：https://www.bilibili.com/video/BVxxxxx
  B站短链：b23.tv/xxxxx
  小红书：xiaohongshu.com 或 xhslink.com 短链
  抖音：https://www.douyin.com/video/xxxxx
  抖音分享页：https://www.douyin.com/share/video/xxxxx
  抖音短链：v.douyin.com/xxxxx
  微博：weibo.com / weibo.cn / video.weibo.com
  西瓜视频：ixigua.com
  AcFun：acfun.cn
  也可以直接粘贴 BV号（如 BV1xx411c7mD）
一次可以粘贴多条，每条之间敲回车或空格分开。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第二步：选择保存位置
点击"浏览…"按钮，选择下载视频保存的文件夹。
建议选桌面或"下载"文件夹，方便找到。

第三步：开始下载
点击右下角的"开始下载"，等待完成即可。
进度条走到100%即为下载完成。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
关于画质和登录
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
普通视频：直接下载，无需设置。
抖音：必须设置 cookies（不登录也行，先访问一次 douyin.com 并通过验证码）。
B站 1080P+ / 会员内容：需要登录。
微博 / 西瓜视频 / AcFun：多数视频直接下载，遇到"需要登录"再设置 cookies 即可。

获取 cookies（推荐）：
1. 在浏览器里正常打开过 B站 / 小红书 / 抖音（抖音通过一次验证码）
2. 回到下载器，点击"自动获取Cookies"按钮
3. 程序会自动从已安装的浏览器读取 cookies，无需手动导出
   下拉框里的浏览器来自本机实际安装情况，日志里会写明这次扫描了哪些浏览器。
如果提示没找到，先按第 1 步访问网站，再点一次即可。

手动获取（备用）：
1. 在 Chrome 应用商店搜索安装扩展：Get cookies.txt LOCALLY
2. 在对应网站页面点击扩展图标，点"Export"导出 cookies.txt
3. 回到下载器，点击"选择…"按钮，找到导出的 cookies.txt
也可以在下拉框里选择浏览器（如 chrome / edge / 360极速浏览器），自动读取浏览器登录态。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
常见问题
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
下载失败：可能是网络问题或视频被删，稍后再试。
小红书解析失败：链接必须用 App「分享 → 复制链接」得到，网页地址栏地址通常不完整。
抖音提示需要 cookies：先在浏览器访问 douyin.com 并通过验证码，再点"自动获取Cookies"。
弹出"需要登录"：请按上方登录方法操作。
进度卡住：点"停止"后再重新"开始下载"。
找不到文件：检查保存目录设置，文件名是视频标题。
提示"412"风控：软件已自动重试，多试几次通常就能下。\
"""
        win = tk.Toplevel(self.root)
        win.title("使用说明")
        win.geometry("660x760")
        win.resizable(False, False)
        win.grab_set()
        win.transient(self.root)
        msg = tk.Message(win, text=text, font=("Microsoft YaHei UI", 10), justify="left", anchor="n")
        msg.pack(fill="both", expand=True, padx=16, pady=12)
        ttk.Button(win, text="知道了", command=win.destroy).pack(pady=(0, 10))

    def _prepare_ffmpeg(self):
        self._log("正在检查 ffmpeg…")
        try:
            if core.find_ffmpeg():
                self._log("已找到 ffmpeg，跳过下载")
                return
        except Exception:
            pass
        size_mb = getattr(core, "FFMPEG_WHEEL_SIZE", 31246824) / 1024 / 1024
        self._log(f"正在下载 ffmpeg 组件（约 {size_mb:.1f} MB，仅首次）…")
        step = {"last": -10}

        def progress(received, total):
            if not total:
                return
            pct = min(100, int(received * 100 // total))
            if pct - step["last"] < 10:
                return
            step["last"] = pct
            self._log(f"  ffmpeg 下载中 {pct}%")
            self.queue.put(ProgressEvent(status="ffmpeg", percent=pct))

        try:
            path = core.ensure_ffmpeg(progress=progress, log=self._log)
        except Exception as exc:
            self._log(f"  ffmpeg 准备失败: {exc}")
            path = None
        if path:
            self._log(f"ffmpeg 已就绪: {path}")
        else:
            self._log("ffmpeg 下载失败，音视频合并需要它。请检查网络后重试，或改用完整版（内置 ffmpeg）。")

    def _make_hook(self, idx: int, total: int):
        def hook(d):
            status = d.get("status")
            if status == "downloading":
                p = d.get("_percent_str", "0%").strip().replace("%", "")
                try:
                    pct = float(p)
                except ValueError:
                    pct = 0.0
                self.queue.put(ProgressEvent(
                    status="downloading",
                    percent=pct,
                    speed=d.get("_speed_str", "").strip(),
                    eta=d.get("_eta_str", "").strip(),
                    filename=d.get("filename", ""),
                ))
            elif status == "finished":
                self.queue.put(ProgressEvent(status="merging", percent=99, filename=d.get("filename", "")))
            elif status == "error":
                err = d.get("error")
                try:
                    detail = str(err)
                except Exception:
                    detail = "未知错误"
                self.queue.put(ProgressEvent(status="error", error=detail))
        return hook

    # ---------------- Polling ----------------
    def _poll_queue(self):
        try:
            while True:
                ev = self.queue.get_nowait()
                self._apply_event(ev)
        except queue.Empty:
            pass
        self.poll_id = self.root.after(100, self._poll_queue)

    def _friendly_hint(self, text: str, platform: str = "") -> str:
        low = (text or "").lower()
        if "xsec_token" in low or "xiaohongshu" in low or "小红书" in text or platform == "xiaohongshu":
            if "分享" in text:
                return ""
            return (
                "小红书链接必须用 App「分享 → 复制链接」得到的完整链接（带 xsec_token 等参数）。\n"
                "只把网址栏里的地址粘进来通常会失败。"
            )
        if platform == "douyin" or "douyin" in low or "抖音" in text:
            if "cookie" in low or "登录" in text or platform == "douyin":
                if "自动获取" in text or "重试" in text:
                    return ""
                return (
                    "请在浏览器里打开 douyin.com、正常看完一个视频并通过验证码，\n"
                    "再回到本软件点“自动获取Cookies”，然后重新下载。"
                )
        return ""

    def _apply_event(self, ev: ProgressEvent):
        if ev.status == "task_start":
            self.title_var.set(ev.title)
            self.detail_var.set(ev.filename or "准备中…")
            self.progress["value"] = 0
        elif ev.status == "downloading":
            self.progress["value"] = ev.percent
            self.detail_var.set(f"{ev.percent:.1f}%   速度 {ev.speed}   剩余 {ev.eta}")
            self.status_var.set(f"下载中 {ev.percent:.1f}%")
        elif ev.status == "merging":
            self.progress["value"] = 99
            self.detail_var.set("合并/后处理中…")
        elif ev.status == "ffmpeg":
            self.progress["value"] = ev.percent
            self.detail_var.set(f"正在下载 ffmpeg 组件 {ev.percent}%（仅首次）")
            self.status_var.set(f"下载 ffmpeg {ev.percent}%")
        elif ev.status == "parsed":
            self.title_var.set(ev.title)
            self.detail_var.set(ev.filename)
        elif ev.status == "error":
            text = ev.error or ""
            self._log(f"错误: {text}")
            hint = self._friendly_hint(text, ev.title or "")
            if hint:
                self.status_var.set("出错")
                messagebox.showwarning("下载失败", f"{text}\n\n{hint}")
            elif "需要登录" in text:
                self.status_var.set("需要登录")
                messagebox.showwarning("需要登录", text)
            elif "412" in text or "Precondition Failed" in text:
                self.status_var.set("网络被拦截,正在重试…")
            else:
                self.status_var.set("出错")
        elif ev.status == "all_done":
            self.progress["value"] = 100
            self.title_var.set("—")
            self.detail_var.set(ev.filename)
            self.status_var.set(ev.filename)
            self.start_btn.configure(state="normal")
            self.parse_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self._log(ev.filename)

    def on_close(self):
        self.stop_flag.set()
        if self.poll_id:
            try:
                self.root.after_cancel(self.poll_id)
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = DownloaderGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
