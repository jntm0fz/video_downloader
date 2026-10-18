# B站 / 小红书 / 抖音 / 微博 / 西瓜视频 / AcFun 视频下载器

一个面向 Windows 新手的图形化视频下载器，支持 B站、小红书、抖音、微博、西瓜视频和 AcFun 链接，使用 `yt-dlp` 下载。

## 功能

- B站 BV、av、ep、b23.tv 链接
- 小红书网页链接和 xhslink.com 短链（须用 App「分享 → 复制链接」得到的完整链接）
- 抖音视频页、分享页（douyin.com/share/video）和 v.douyin.com 短链
- 微博视频（weibo.com / weibo.cn / video.weibo.com）
- 西瓜视频（ixigua.com）
- AcFun（acfun.cn）
- 清晰度选择
- 视频+音频、仅视频、仅音频、封面下载
- 批量下载队列
- 下载进度、速度和剩余时间
- 从 `cookies.txt` 或本机已安装的浏览器（含 360、QQ、搜狗等国产浏览器）读取登录态
- ffmpeg 随程序提供，无需用户自行安装（轻量版会在首次下载前自动获取）
- GitHub Releases 自动检查和更新
- 可直接打包为单文件 EXE

## 完整版 / 轻量版

两个版本功能完全相同，区别只在 ffmpeg（音视频合并组件）怎么来：

| | 完整版 | 轻量版 |
| --- | --- | --- |
| 文件名 | `video-downloader.exe` | `video-downloader-lite.exe` |
| 体积 | 约 52 MB | 约 23 MB |
| ffmpeg | 已内置，离线可用 | 首次下载视频前自动下载约 29.8 MB |
| 适合 | 新手、网络不稳定、想开箱即用 | 体积敏感、能联网、愿意等第一次下载 |

> 文件名用英文是因为 GitHub 会给中文资源名替换成 `.`（例如 `B站视频下载器.exe` 会变成 `B.exe`），
> 那样用户下载下来就是个坏名字。程序界面和提示仍然全是中文。

- 完整版推荐给新手：拷到任何地方都能直接跑，不需要联网获取 ffmpeg。
- 轻量版第一次点“开始下载”时，软件会提示并下载约 29.8 MB 的 ffmpeg，保存在 EXE 同一个目录下；之后一直复用，不会再下载。下载过程中日志和进度条会显示百分比。
- 如果轻量版的 ffmpeg 下载失败（例如断网），软件仍会继续尝试下载视频；只是遇到需要合并音视频的视频会失败。此时可以联网重试，或改用完整版。
- 删掉 EXE 同目录下的 ffmpeg，下次下载前会重新下载一次。

## 使用

双击 `video-downloader.exe` 或 `video-downloader-lite.exe`，输入链接，选择保存目录，点击“开始下载”。

需要下载高清、会员或私密内容时，在软件的下拉框里选择本机已安装的浏览器登录态，或使用 `cookies.txt`。

抖音视频需要 cookies。点击软件里的“自动获取Cookies”按钮，即可自动从本机已安装、且访问过对应网站的浏览器中读取 cookies，无需手动导出。若提示未找到，先在浏览器打开一次该网站（抖音需通过验证码），再点一次按钮即可。

微博、西瓜视频、AcFun 多数视频可直接下载；遇到“需要登录”时按上面的方法设置 cookies。

ffmpeg 无需用户另行安装：完整版已内置；轻量版会在首次下载视频前自动下载约 29.8 MB 到 EXE 同目录并复用。

## 开发运行

```bash
python -m pip install -r requirements.txt
python gui.py
```

## 打包

```bash
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --clean --noconfirm bilibili.spec
```

生成的程序位于 `dist/video-downloader.exe`（完整版）；打轻量版时设置环境变量 `BILIBILI_LITE=1` 再执行上面的命令，产物为 `dist_lite/video-downloader-lite.exe`。

## 自动更新

软件通过 GitHub Releases 检查更新。首次使用点击“更新设置”，填写 GitHub 仓库，例如 `用户名/仓库名`。之后点击“检查更新”，有新版本时会下载并自动替换当前 EXE。

发布新版本时，推一个 `v1.1.0` 这样的 tag，GitHub Actions 会自动构建并上传
`video-downloader.exe`（完整版）与 `video-downloader-lite.exe`（轻量版）。

## 依赖

- Python 3.10+
- `yt-dlp`
- `requests`
- `tqdm`
- `curl-cffi`
- `imageio-ffmpeg`（提供 ffmpeg，用于音视频合并；完整版随打包内置，轻量版在首次下载前自动获取）

## 开源许可

本项目采用 [MIT License](LICENSE) 开源。
