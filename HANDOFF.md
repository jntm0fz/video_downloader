# 交接文档 — B站 / 小红书 / 抖音 视频下载器

> 面向接手本项目的其他 AI / 开发者。请先通读本文件再改动代码。

## 1. 项目目标

一个面向 Windows 新手用户的图形化视频下载器，支持 B站、小红书、抖音，并顺带支持微博、
西瓜视频、AcFun（凡 `yt-dlp` 有 extractor 的平台基本都能用），基于 `yt-dlp`，
可打包成单文件 EXE，**分「完整版」（内置 ffmpeg，约 52 MB）与「轻量版」（不含 ffmpeg，约 23 MB，
首次下载前自动抓取）**，用户无需另行安装 ffmpeg，并带有基于 GitHub Releases 的自动更新功能。

- 界面、注释、日志、用户提示：全部使用**简体中文**。
- 默认保存目录：`~/Downloads/video`。
- 默认清晰度：`1080`。

## 2. 运行环境（重要，容易踩坑）

- 操作系统：Windows（开发机为 Windows 11）。
- 交互终端：**PowerShell 5.1**。
  - 不支持 `&&`，请用 `;` 或 `cmd1; if ($?) { cmd2 }`。
  - 路径含中文/空格时用 `& "路径"` 或 `-LiteralPath`。
- Python：`D:\files\杨子韬的文件夹\编程\Python\python.exe`（3.12.5）。
  - pip 用 `& "…python.exe" -m pip …`，机器上**没有**裸 `pip`。
- ffmpeg：**已通过 `imageio-ffmpeg` 内置进「完整版」EXE**，普通用户无需自行安装；
  「轻量版」不含，首次下载前用 `ensure_ffmpeg()` 从镜像抓 wheel 解出，存到 EXE 同目录。
  - `find_ffmpeg()` 探测顺序：环境变量 `FFMPEG_PATH` → 冻结时 `sys._MEIPASS\ffmpeg.exe`（完整版）
    → `imageio_ffmpeg.get_ffmpeg_exe()`（仅开发态）→ `local_ffmpeg_path()`（轻量版已下载的）
    → 写死的候选路径 → `shutil.which("ffmpeg")`。每步异常都吞掉继续兜底。
  - 开发机本机另有 `F:\video\tool\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe`（8.1.1 完整版）。
- 已安装依赖：`yt-dlp 2026.8.19`、`tqdm`、`requests`、`curl-cffi`、`imageio-ffmpeg 0.6.0`、`pyinstaller 6.22.2`。
- Git：已安装（`C:\Program Files\Git\cmd\git.exe`）。`gh` **未安装**。

## 3. 目录结构

```
bilibili下载器/
├─ downloader.py        核心下载模块（yt-dlp 封装、平台识别、URL 归一化、报错翻译、CLI）
├─ gui.py               tkinter 界面（入口文件，PyInstaller 以它为主脚本）
├─ cookies_tool.py      自动从浏览器读取 cookies
├─ updater.py           GitHub Releases 自动更新
├─ bilibili.spec        PyInstaller 单文件打包配置
├─ run.bat              源码方式启动 GUI
├─ requirements.txt     依赖清单
├─ README.md            用户向说明
├─ HANDOFF.md           本文件
├─ .github/workflows/release.yml   打 tag 时自动构建并上传 Release
├─ .gitignore
├─ build/  dist/  dist_lite/   PyInstaller 产物（已 gitignore）
├─ dist/B站视频下载器.exe          完整版成品（内置 ffmpeg，约 52 MB）
└─ dist_lite/B站视频下载器-轻量版.exe  轻量版成品（不含 ffmpeg，约 23 MB）
```

## 4. 各模块说明

### 4.1 `downloader.py`（核心）

关键函数（带行号参考，行号可能随改动漂移）：

| 函数 | 作用 |
| --- | --- |
| `detect_platform(url)` | 返回 `bilibili` / `douyin` / `xiaohongshu` / `weibo` / `ixigua` / `acfun` / `other` / `unknown` |
| `platform_headers(platform)` | 按平台返回 Referer/Origin/UA，避免用 B站 Referer 请求抖音 |
| `extract_bvid(url)` | 从链接/文本抽取 BV/av/ep/ss 号 |
| `normalize_url(url)` | 归一化链接：BV→视频页、抖音分享链/短链→`douyin.com/video/<id>`、其他短链原样返回 |
| `friendly_error(err_str, platform)` | 把 yt-dlp 英文报错翻译成中文提示 |
| `find_ffmpeg()` | 探测 ffmpeg（优先内置 / 已下载） |
| `ensure_ffmpeg(progress, log)` | 轻量版按需从镜像下载 ffmpeg，返回路径；失败返回 `None` |
| `build_ydl_opts(...)` | 组装 yt-dlp 选项（清晰度、模式、headers、cookies、impersonate） |
| `probe(url, ...)` | 只解析元信息（不下载），带 412 重试 |
| `get_formats(...)` | 返回可用格式列表 |
| `download(url, save_dir, ...)` | 下载主入口，带 412 重试 |
| `main_cli()` | 命令行入口（`python downloader.py <URL> [目录] [清晰度]`） |

平台要点：

- **B站**：`extractor_args={"bilibili":{"client":"web"}}`；针对 412 风控做 `impersonate`
  浏览器指纹 + 重试。指纹从 `YoutubeDL()._request_director.handlers["CurlCFFI"].supported_targets`
  里挑 chrome 目标（代码里优先 133/136/142/145/146/150）。
  **注意**：`ImpersonateTarget("chrome120")` 这种字符串写法无效，只能用 supported_targets 里的对象。
- **抖音**：`yt-dlp` 有 `DouyinIE`，但**必须有 cookies**（只用 `s_v_web_id` 判定，
  报错 "Fresh cookies (not necessarily logged in) are needed"）。程序会翻译成中文提示。
  - `DouyinIE._VALID_URL` 只认 `douyin.com/video/<纯数字>`；`douyin.com/share/video/<id>`、
    `iesdouyin.com/share/video/<id>/` 以及 `v.douyin.com/xxxx` 短链都由
    `normalize_url()` 归一化后再交给 yt-dlp。
  - 实测：`v.douyin.com` 短链 302 常落到 `iesdouyin.com/share/user/...` **用户主页**
    （不是视频页），此时 yt-dlp 报 `Unsupported URL`；`normalize_url()` 会识别并抛中文提示，
    引导用户改用 App「分享 → 复制链接」拿视频链接。
  - 实测：无头/裸请求伪造 `s_v_web_id` 请求 `aweme/v1/web/aweme/detail/` 固定 **403
    `Blocked by ArgusSecurityPlugin`**，**不要试图伪造**；`iesdouyin` 分享页也已不含
    `play_addr` 直链。结论：只能读用户已通过验证的真实浏览器 cookies。
  - 实测：无头浏览器访问 douyin.com 会被拦截到「验证码中间页」，**无法纯自动抓取**。
  - 因此自动获取 cookies 只能从用户已通过验证的真实浏览器读取（见 `cookies_tool.py`）。
- **小红书**：`yt-dlp` 有 `XiaoHongShuIE`，链接原样交给 yt-dlp。
  其 `_TESTS` 用例的 URL **带 `xsec_token=`**，裸链接（去掉 query 后）大概率拿不到内容 →
  `friendly_error()` 会提示用户用 App「分享 → 复制链接」重新获取完整链接。
- **微博 / 西瓜 / AcFun**：`yt-dlp` 分别有 `WeiboIE` / `IxiguaIE` / `AcFunVideoIE`，
  已纳入 `detect_platform()` 与 `platform_headers()`，不需要额外适配。

### 4.2 `gui.py`（入口）

- 主类：`DownloaderGUI`（`gui.py:48`），入口函数 `main()`（`gui.py:608`）。
- 通过 `queue.Queue` + `root.after` 在主线程刷 UI，工作线程只往队列放 `ProgressEvent`。
- 主要控件：链接输入、清晰度、下载内容（视频+音频/仅视频/仅音频/封面）、保存目录、
  cookies 区（cookies.txt 路径输入框 + 选择文件按钮 + 浏览器下拉 + 「自动获取Cookies」按钮）、
  解析信息、开始下载、停止、使用说明、检查更新、更新设置、清空日志、打开目录。
- `_on_start()` 里：若含抖音链接且未设置任何 cookies，会先自动尝试从浏览器获取（见
  `cookies_tool.auto_get_cookies(["douyin"])`）。
- 打包适配：`sys.frozen` 时把 `sys._MEIPASS` 加入 `sys.path`，以便 import 打进去的 `downloader.py`。

### 4.3 `cookies_tool.py`（自动获取 cookies）

- 用 `yt_dlp.cookies.extract_cookies_from_browser(browser)` 读取本机浏览器 cookies。
- 浏览器分两类：
  - yt-dlp 原生支持：chrome / edge / brave / firefox / chromium / opera / vivaldi / whale。
  - 国产 Chromium 内核浏览器（360极速 / 360安全 / QQ / 搜狗 / 猎豹 / 2345 / UC）：
    yt-dlp **不认这些浏览器名**（会 `ValueError: unsupported browser`），本模块改为
    把它们的 **profile 目录**（如 `…\User Data\Default`）当作 `profile` 传给 `'chrome'`。
    实测 `yt_dlp.cookies._extract_chrome_cookies` 中当 `profile` 是路径时
    `search_root = profile`（`os.walk` 递归找 `Cookies`），`browser_dir = os.path.dirname(profile)`
    用于找 `Local State`（v10 密钥）；所以**必须传 profile 目录，不能传 `User Data` 根目录**。
- `available_browsers()`：返回本机实际存在且含 profile 的浏览器 `[(显示名, profile目录)]`，
  GUI 下拉框用它填充。
- 平台域名映射在 `PLATFORM_DOMAINS`（B站含 b23.tv；抖音含 douyin/iesdouyin/bytedance；
  小红书含 xiaohongshu/xhslink；另含微博/西瓜/AcFun）。
- `auto_get_cookies(platforms, out_path=None)`：合并保存为 `cookies_auto.txt`
  （优先放在 exe 同目录，不可写则退回系统临时目录），返回
  `{path, details, found, missing, total}`。
- `open_platform_sites(platforms)`：用默认浏览器打开对应网站，方便用户先去过一次验证。
- 已知限制：
  - 部分国产浏览器目录存在但**没有 `Cookies` 数据库**（实测本机 360 极速即是），
    此时会报「不可用」而不是崩溃。
  - Edge/Chrome 类浏览器**正在运行时**，其 Cookies 数据库可能被锁（yt-dlp 会尝试复制，
    有时失败，报 "Could not copy Chrome cookie database"）→ 让用户先关闭浏览器。
  - 用户从未访问过某站点 → 该站点没有 cookies，需要先访问（抖音需过验证码）。
  - 新版 Chrome 的 App-Bound 加密可能导致解密失败；yt-dlp 已尽量兼容。

### 4.4 `updater.py`（自动更新）

- `APP_VERSION = "1.1.0"`，此版本号需与新 Release 的 tag（如 `v1.1.0`）比较。
- 更新源：`https://api.github.com/repos/{owner}/{repo}/releases/latest`。
- 仓库地址由用户在界面「更新设置」里输入（`用户名/仓库名`），保存到 exe 同目录
  `update_config.json`。
- `check_update()` → 返回新版本信息；`install_update()` 下载
  `B站视频下载器.exe.new`，再生成一个 `.cmd` 助手脚本，等当前进程退出后替换
  exe 并自删。GUI 下载完成后会 `root.destroy()` 让进程退出以触发替换。
- 资产名匹配按自身 EXE 名区分版本：轻量版优先 `B站视频下载器-轻量版.exe`，
  完整版优先 `B站视频下载器.exe`（见 `updater.select_asset()` / `current_exe_name()`）。
- **发布流程**：给仓库 push 一个 `v*` tag，`.github/workflows/release.yml` 会在
  windows runner 上 `pip install -r requirements.txt` + PyInstaller 构建并上传 Release。
  改版本号只需改 `updater.py` 的 `APP_VERSION`（GUI 标题会自动带版本号）。

## 5. 构建 / 运行命令

```powershell
# 源码运行
& "D:\files\杨子韬的文件夹\编程\Python\python.exe" gui.py

# 语法检查
& "D:\files\杨子韬的文件夹\编程\Python\python.exe" -m py_compile downloader.py gui.py updater.py cookies_tool.py

# 打包完整版（内置 ffmpeg）
& "D:\files\杨子韬的文件夹\编程\Python\python.exe" -m PyInstaller --clean --noconfirm bilibili.spec

# 打包轻量版（不含 ffmpeg，dist_lite 目录）
$env:BILIBILI_LITE = "1"
& "D:\files\杨子韬的文件夹\编程\Python\python.exe" -m PyInstaller --clean --noconfirm --distpath dist_lite bilibili.spec
Remove-Item Env:BILIBILI_LITE
```

产物：`dist\B站视频下载器.exe`（完整版，约 52 MB）与
`dist_lite\B站视频下载器-轻量版.exe`（约 23 MB），均为单文件 `console=False`。

打包注意：
- `bilibili.spec` 的 `hiddenimports` 已包含 `yt_dlp.extractor.bilibili`、
  `yt_dlp.extractor.tiktok`、`yt_dlp.extractor.xiaohongshu`、`curl_cffi`、
  `updater`、`cookies_tool` 等。**新增直依赖模块时记得加进来**。
  （注意：**没有** `Cryptodome`，yt-dlp 解密浏览器 cookie 走的是 Windows DPAPI，不需要它。）
- 双版本靠环境变量 `BILIBILI_LITE=1` 切换：置 1 时 `binaries=[]`、EXE 名改成
  `B站视频下载器-轻量版`；不置则维持完整版行为。
- **`excludes` 里必须有 `'imageio_ffmpeg'`（两个版本都要）**，这是体积的关键：
  `downloader.py` 里 `find_ffmpeg()` 有一句静态 `import imageio_ffmpeg`，PyInstaller 的
  modulegraph 会因此把整个包纳入依赖图，而 `_pyinstaller_hooks_contrib` 的
  `hook-imageio_ffmpeg.py` 又会执行 `collect_data_files('imageio_ffmpeg', subdir="binaries")`，
  **无条件**把 83.58 MB 的 `ffmpeg-win-x86_64-v7.1.exe` 收进 `datas`。
  仅靠过滤 `hiddenimports` 无效（它只管 hiddenimports，不管 hook 的 datas）。
  实测代价：漏掉这条 `excludes` 时，轻量版会从 22.67 MB 涨到 52.35 MB，
  完整版更会因同一份二进制被打进两次而至 86.0 MB。
- 完整版的 ffmpeg 由 `binaries` 打进包：`imageio_ffmpeg.get_ffmpeg_exe()` 取到的二进制被重命名为
  `ffmpeg.exe` 放在包根目录，运行时经 `sys._MEIPASS` 找到（87,638,016 字节，是体积主因）。
  打包完可核对 `build*/bilibili/PKG-00.toc` 条目表：完整版应**恰好 1 条** `ffmpeg.exe`，
  轻量版应为 **0 条**。
- 轻量版运行时用 `ensure_ffmpeg()` 从 PyPI 镜像抓 `imageio_ffmpeg` 的 wheel（约 29.8 MB），
  校验 sha256 后解出里面的 `ffmpeg-win-x86_64-v7.1.exe`，`os.replace()` 成 EXE 同目录的 `ffmpeg.exe`。
  镜像顺序：清华 → 阿里 → 腾讯 → 北外 → 官方 `files.pythonhosted.org`。
  （实测清华源会返回 403，会自动切到阿里源成功，5 源顺序兜底正常。）
- 冻结态下 `find_ffmpeg()` 里那句 `import imageio_ffmpeg` 会 ImportError，已被 `except Exception`
  吞掉并继续走 `sys._MEIPASS\ffmpeg.exe` / 已下载的 `ffmpeg.exe` 兜底，属预期行为、不要"修"。
- `.github/workflows/release.yml` 会连打两个版本并一起上传 Release（打 tag 时）。
- 自动更新按自身 EXE 名区分：轻量版装轻量版、完整版装完整版（见 `updater.current_exe_name()`）。
- `datas` 里放了 `downloader.py`，`gui.py` 靠 `sys._MEIPASS` 找到。
- 重新打包前若报 `PermissionError: …exe 拒绝访问`，说明旧的 EXE 仍在运行：
  `Get-Process -Name 'B站视频下载器' | Stop-Process -Force`。
- 单文件 EXE 启动后会有**两个进程**（bootloader + 真身），测试时要一起结束。

## 6. 当前 Git 状态

- 本地仓库已配好，分支 `main`，已有 3 个提交：

  | commit | 说明 |
  | --- | --- |
  | `3fa155e` | 加 `.gitattributes`：bat/cmd 强制 CRLF，源码统一 LF |
  | `159a8f8` | 版本号升到 1.1.0（新增轻量版、多平台、按需 ffmpeg） |
  | `d3d2e48` | 视频下载器 1.0.0：B站/抖音/小红书多平台，完整版+轻量版双打包 |

- 身份：`user.name = jntm0fz`，`user.email = 3779949164@qq.com`。
- `.gitattributes` 已加：`*.bat` / `*.cmd` 强制 CRLF（否则 `run.bat` 在 Windows 上会出问题），
  源码统一 LF，`*.exe` / `*.dll` / `*.whl` 按二进制存。
- **尚未配置 remote**，因为当时 GitHub 连不上，没有 push。
- 工作区干净（`git status` 无输出）。`build/` `dist/` `dist_lite/` `__pycache__/`
  `cookies*.txt` `update_config.json` 等均由 `.gitignore` 排除。

后续要上传（GitHub 恢复后）：

```powershell
git remote add origin https://github.com/<用户名>/<仓库名>.git
git push -u origin main
# 首次发版：推送 tag 触发 .github/workflows/release.yml 自动构建
git tag v1.1.0
git push origin v1.1.0
```

首次 `push` / `push tag` 会弹浏览器/凭据框（credential helper = `manager`），登录一次即可，
之后自动记住。

## 7. 已知问题 / 待办

1. **抖音的 cookies 仍非“全自动”**：受验证码限制，必须先由用户在浏览器访问并通过验证。
   若要真正的全自动，需要引入浏览器自动化（Selenium / Playwright / nodriver / DrissionPage），
   目前均**未安装**，且会显著增大体积。伪造 `s_v_web_id` 已实测无效（403 ArgusSecurityPlugin）。
   此外 `v.douyin.com` 短链可能 302 到用户主页而非视频页，已由 `normalize_url()` 给中文提示。
2. `gui.py` 中「仅视频」目前等价于「视频+音频」（未单独区分），见 `_on_start` 的 `mode_map`。
3. 抖音/小红的“封面”下载依赖 `writethumbnail`，个别视频可能没有缩略图。
4. `updater` 未做签名校验，替换 exe 前只检查文件非空。
5. `probe()` 的 `friendly_error` 匹配关键词（cookies/login/wbi）较宽，可能误判个别错误文案。

## 8. 改代码时的注意事项

- 保持中文 UI/提示。代码里尽量少加注释，只在关键逻辑（风控重试、ffmpeg 校验、双版本分支）
  处保留简短中文说明；现有各模块的函数 docstring 请保留。
- 平台相关逻辑尽量走 `detect_platform()` / `platform_headers()`，不要在 `build_ydl_opts`
  里写死单一平台的 header。
- `yt-dlp` 版本较新，内部 API（如 `_request_director`、`supported_targets`）可能随版本变化，
  升级 yt-dlp 后需回归 412 风控逻辑。
- 改完务必 `py_compile`，并重新打包启动一次 EXE 验证。
