"""
B站视频下载器核心模块
基于 yt-dlp 实现，支持登录态、清晰度选择、下载进度回调。
"""
import os
import sys
import re
import json
import time
import shutil
import hashlib
import zipfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List

try:
    import yt_dlp
except ImportError:
    print("缺少依赖 yt-dlp，请先运行：pip install yt-dlp", file=sys.stderr)
    raise

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


# 常见 B 站链接正则
BV_PATTERN = re.compile(r"BV[A-Za-z0-9]{10}")
AV_PATTERN = re.compile(r"av(\d+)", re.IGNORECASE)
EP_PATTERN = re.compile(r"ep(\d+)", re.IGNORECASE)
SS_PATTERN = re.compile(r"ss(\d+)", re.IGNORECASE)
B23_PATTERN = re.compile(r"https?://b23\.tv/\S+", re.IGNORECASE)
BILI_URL = re.compile(r"https?://(www\.)?bilibili\.com/\S+", re.IGNORECASE)

# 抖音 / 小红书
DOUYIN_HOST = re.compile(r"(?:^|[/.])douyin\.com|iesdouyin\.com", re.IGNORECASE)
DOUYIN_SHORT = re.compile(r"https?://v\.douyin\.com/\S+", re.IGNORECASE)
DOUYIN_VIDEO = re.compile(r"/video/(\d+)")
DOUYIN_USER_PAGE = re.compile(r"/(?:share/)?user/", re.IGNORECASE)
DOUYIN_ID = re.compile(
    r"(?:douyin\.com/(?:share/)?video/|iesdouyin\.com/share/video/)(\d+)",
    re.IGNORECASE,
)
XHS_HOST = re.compile(r"xiaohongshu\.com|xhslink\.com", re.IGNORECASE)
WEIBO_HOST = re.compile(r"(?:^|[/.])weibo\.com|weibo\.cn", re.IGNORECASE)
IXIGUA_HOST = re.compile(r"(?:^|[/.])ixigua\.com", re.IGNORECASE)
ACFUN_HOST = re.compile(r"(?:^|[/.])acfun\.cn", re.IGNORECASE)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

FFMPEG_WHEEL_SHA256 = "02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a"
FFMPEG_WHEEL_SIZE = 31246824
FFMPEG_WHEEL_PATH = (
    "/packages/2c/c6/fa760e12a2483469e2bf5058c5faff664acf66cadb4df2ad6205b016a73d/"
    "imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl"
)
FFMPEG_WHEEL_URLS = [
    "https://pypi.tuna.tsinghua.edu.cn" + FFMPEG_WHEEL_PATH,
    "https://mirrors.aliyun.com/pypi" + FFMPEG_WHEEL_PATH,
    "https://mirrors.cloud.tencent.com/pypi" + FFMPEG_WHEEL_PATH,
    "https://mirrors.bfsu.edu.cn/pypi/web" + FFMPEG_WHEEL_PATH,
    "https://files.pythonhosted.org" + FFMPEG_WHEEL_PATH,
]
FFMPEG_WHEEL_NAMES = ["清华源", "阿里源", "腾讯源", "北外源", "官方源"]


def ffmpeg_dir() -> str:
    """存放自动下载的 ffmpeg 的目录。"""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        if base and os.path.isdir(base) and os.access(base, os.W_OK):
            return base
    except Exception:
        pass
    return tempfile.gettempdir()


def local_ffmpeg_path() -> str:
    """自动下载的 ffmpeg 的目标路径。"""
    return os.path.join(ffmpeg_dir(), "ffmpeg.exe" if os.name == "nt" else "ffmpeg")


def _extract_ffmpeg_from_wheel(wheel_path: str, target: str) -> Optional[str]:
    part = target + ".part"
    with zipfile.ZipFile(wheel_path) as zf:
        names = [
            n for n in zf.namelist()
            if n.lower().endswith(".exe") and "binaries/" in n.lower()
        ]
        if not names:
            return None
        biggest = max(names, key=lambda n: zf.getinfo(n).file_size)
        with zf.open(biggest) as src, open(part, "wb") as dst:
            shutil.copyfileobj(src, dst)
    if not os.path.isfile(part) or os.path.getsize(part) <= 0:
        try:
            os.remove(part)
        except Exception:
            pass
        return None
    os.replace(part, target)
    return target


def ensure_ffmpeg(
    progress: Optional[Callable[[int, int], None]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """确保有一份可用的 ffmpeg，没有就自动下载。"""
    def _log(msg: str) -> None:
        if log:
            try:
                log(msg)
            except Exception:
                pass

    found = find_ffmpeg()
    if found:
        return found

    target = local_ffmpeg_path()
    for idx, url in enumerate(FFMPEG_WHEEL_URLS):
        name = FFMPEG_WHEEL_NAMES[idx] if idx < len(FFMPEG_WHEEL_NAMES) else url
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".whl")
            os.close(fd)
            req = urllib.request.Request(url, headers={"User-Agent": DESKTOP_UA})
            digest = hashlib.sha256()
            received = 0
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = 0
                try:
                    total = int(resp.headers.get("Content-Length") or 0)
                except Exception:
                    total = 0
                if total <= 0:
                    total = FFMPEG_WHEEL_SIZE
                with open(tmp_path, "wb") as fh:
                    while True:
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        fh.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        if progress:
                            try:
                                progress(received, total)
                            except Exception:
                                pass
            if received <= 0:
                _log(f"{name}下载内容为空，换下一个源")
                continue
            if received != FFMPEG_WHEEL_SIZE:
                _log(f"{name}大小不符（{received} 字节），换下一个源")
                continue
            if digest.hexdigest().lower() != FFMPEG_WHEEL_SHA256.lower():
                _log(f"{name}校验失败，换下一个源")
                continue
            if _extract_ffmpeg_from_wheel(tmp_path, target):
                _log(f"ffmpeg 已就绪：{target}")
                return target
            _log(f"{name}解压失败，换下一个源")
        except Exception as e:
            _log(f"{name}下载失败, 换下一个源（{e}）")
        finally:
            if tmp_path and os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    _log("所有下载源都失败了，请手动下载 ffmpeg.exe 放到程序目录")
    return None


def detect_platform(url: str) -> str:
    """判断链接属于哪个平台。"""
    url = (url or "").strip()
    if not url:
        return "unknown"
    if DOUYIN_HOST.search(url):
        return "douyin"
    if XHS_HOST.search(url):
        return "xiaohongshu"
    if WEIBO_HOST.search(url):
        return "weibo"
    if IXIGUA_HOST.search(url):
        return "ixigua"
    if ACFUN_HOST.search(url):
        return "acfun"
    if BILI_URL.search(url) or B23_PATTERN.search(url):
        return "bilibili"
    if extract_bvid(url):
        return "bilibili"
    return "other"


def platform_headers(platform: str) -> Dict[str, str]:
    """按平台给出合适的请求头。"""
    if platform == "douyin":
        return {
            "User-Agent": DESKTOP_UA,
            "Referer": "https://www.douyin.com/",
            "Origin": "https://www.douyin.com",
        }
    if platform == "xiaohongshu":
        return {
            "User-Agent": DESKTOP_UA,
            "Referer": "https://www.xiaohongshu.com/",
        }
    if platform == "bilibili":
        return {
            "User-Agent": DESKTOP_UA,
            "Referer": "https://www.bilibili.com",
            "Origin": "https://www.bilibili.com",
        }
    if platform == "weibo":
        return {
            "User-Agent": DESKTOP_UA,
            "Referer": "https://weibo.com/",
        }
    if platform == "ixigua":
        return {
            "User-Agent": DESKTOP_UA,
            "Referer": "https://www.ixigua.com/",
            "Origin": "https://www.ixigua.com",
        }
    if platform == "acfun":
        return {
            "User-Agent": DESKTOP_UA,
            "Referer": "https://www.acfun.cn/",
            "Origin": "https://www.acfun.cn",
        }
    return {"User-Agent": DESKTOP_UA}


def extract_bvid(url: str) -> Optional[str]:
    """从各种形式的链接/输入里抽出 BV 号或 av 号。"""
    if not url:
        return None
    m = BV_PATTERN.search(url)
    if m:
        return m.group(0)
    m = AV_PATTERN.search(url)
    if m:
        return f"av{m.group(1)}"
    m = EP_PATTERN.search(url)
    if m:
        return f"ep{m.group(1)}"
    m = SS_PATTERN.search(url)
    if m:
        return f"ss{m.group(1)}"
    return None


def normalize_url(url: str) -> str:
    """把用户输入归一化成可识别的 URL。"""
    url = url.strip()
    if not url:
        return url
    if DOUYIN_HOST.search(url):
        m = DOUYIN_ID.search(url)
        if m:
            return f"https://www.douyin.com/video/{m.group(1)}"
        if DOUYIN_SHORT.search(url):
            return resolve_douyin_short(url)
        return url
    if XHS_HOST.search(url):
        return url
    if B23_PATTERN.search(url):
        return url
    bvid = extract_bvid(url)
    if bvid:
        if bvid.startswith("BV"):
            return f"https://www.bilibili.com/video/{bvid}"
        if bvid.startswith("av"):
            return f"https://www.bilibili.com/video/{bvid}"
        if bvid.startswith("ep"):
            return f"https://www.bilibili.com/bangumi/play/{bvid}"
        if bvid.startswith("ss"):
            return f"https://www.bilibili.com/bangumi/play/{bvid}"
    if BILI_URL.search(url):
        return url
    return url


def resolve_douyin_short(url: str) -> str:
    """跟随抖音短链跳转，抽出真正的视频链接。"""
    from urllib.parse import urljoin
    import requests

    session = requests.Session()
    session.headers.update(platform_headers("douyin"))
    current = url
    try:
        for _ in range(6):
            if DOUYIN_VIDEO.search(current):
                break
            if DOUYIN_USER_PAGE.search(current):
                break
            resp = session.get(current, allow_redirects=False, timeout=10)
            loc = resp.headers.get("Location") or resp.headers.get("location")
            if not loc:
                break
            current = urljoin(current, loc)
    except Exception:
        return url
    m = DOUYIN_VIDEO.search(current)
    if m:
        return f"https://www.douyin.com/video/{m.group(1)}"
    if DOUYIN_USER_PAGE.search(current):
        raise yt_dlp.utils.DownloadError(
            "该抖音短链跳转到了用户主页，不是视频页面，无法下载。"
            "请在抖音 App 里打开要下载的视频，点「分享 → 复制链接」，再把复制到的视频链接粘贴进来。"
        )
    return url


def friendly_error(err_str: str, platform: str = "") -> Optional[str]:
    """把 yt-dlp 的英文报错翻译成更好懂的中文提示。"""
    low = err_str.lower()
    if "unsupported url" in low and platform == "douyin":
        return (
            "识别不了这个抖音链接。抖音只支持 https://www.douyin.com/video/数字ID 这种视频链接，"
            "请在抖音 App 里打开视频，点「分享 → 复制链接」后重新粘贴。"
        )
    if platform == "douyin" and ("cookies" in low or "login" in low or "logged" in low or "sign in" in low
                                 or "403" in low or "forbidden" in low or "argus" in low):
        return "抖音必须先在浏览器登录/访问 douyin.com 后点自动获取Cookies，再重试下载。"
    if platform == "xiaohongshu" and ("cookies" in low or "login" in low or "logged" in low
                                      or "sign in" in low or "403" in low or "forbidden" in low
                                      or "xsec" in low or "token" in low or "unable to extract" in low
                                      or "no video formats" in low or "unsupported url" in low):
        return ("小红书链接必须带 App 分享生成的完整参数（如 xsec_token），"
                "请用 App 分享→复制链接重新获取。")
    if "fresh cookies" in low or ("cookies" in low and "needed" in low):
        if platform == "douyin":
            return "抖音必须先在浏览器登录/访问 douyin.com 后点自动获取Cookies，再重试下载。"
        return "该视频需要 cookies 才能下载。请在软件里设置 cookies.txt，或选择已登录的浏览器后重试。"
    if "login" in low or "logged" in low or "sign in" in low:
        return "该视频需要登录才能下载。请在软件里设置 cookies.txt 或选择浏览器登录后重试。"
    if "wbi" in low:
        return "B站需要登录才能下载此视频，请在软件里设置 cookies.txt 或选择浏览器登录。"
    return None


def find_ffmpeg() -> Optional[str]:
    """尽量自动找一份 ffmpeg，没找到就交给 yt-dlp 自己处理。"""
    env = os.environ.get("FFMPEG_PATH")
    if env and os.path.isfile(env):
        return env
    if getattr(sys, "frozen", False):
        try:
            bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "ffmpeg.exe")
            if os.path.isfile(bundled):
                return bundled
        except Exception:
            pass
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    try:
        local = local_ffmpeg_path()
        if local and os.path.isfile(local):
            return local
    except Exception:
        pass
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates = []
    if os.name == "nt":
        candidates += [
            r"F:\video\tool\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    from shutil import which
    return which("ffmpeg")


def build_ydl_opts(
    save_dir: str,
    quality: str = "best",
    download_mode: str = "video",
    cookie_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
    ffmpeg_path: Optional[str] = None,
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    quiet: bool = True,
    platform: str = "bilibili",
) -> Dict[str, Any]:
    """
    quality: best / 1080 / 720 / 480 / 360
    download_mode: video / audio / cover / video+audio(muxed)
    """
    Path(save_dir).mkdir(parents=True, exist_ok=True)

    # 选清晰度
    height_map = {"1080": 1080, "720": 720, "480": 480, "360": 360, "240": 240}
    if quality == "best":
        format_selector = (
            "bestvideo*+bestaudio/best"
            if download_mode == "video"
            else "bestaudio/best"
        )
    elif quality in height_map:
        h = height_map[quality]
        if download_mode == "video":
            format_selector = (
                f"bestvideo[height<={h}]+bestaudio/"
                f"best[height<={h}]/best"
            )
        else:
            format_selector = f"bestaudio/best"
    else:
        format_selector = "bestvideo*+bestaudio/best"

    outtmpl = os.path.join(save_dir, "%(title)s [%(id)s].%(ext)s")

    opts: Dict[str, Any] = {
        "format": format_selector,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": quiet,
        "no_warnings": quiet,
        "noprogress": quiet,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "windowsfilenames": True,
        "writethumbnail": download_mode == "cover",
        "http_headers": platform_headers(platform),
    }

    if platform == "bilibili":
        opts["extractor_args"] = {
            "bilibili": {
                "client": "web",
            }
        }

    # 模拟浏览器,绕过 B站 412 / 抖音风控
    if platform in ("bilibili", "douyin") and not cookie_file and not cookies_from_browser:
        try:
            import yt_dlp
            from yt_dlp.networking.impersonate import ImpersonateTarget
            tmp = yt_dlp.YoutubeDL({"quiet": True})
            curl_handler = tmp._request_director.handlers.get("CurlCFFI")
            chosen = None
            if curl_handler is not None:
                for t in curl_handler.supported_targets:
                    if t.client == "chrome" and t.version in ("133", "136", "142", "145", "146", "150"):
                        chosen = t
                        break
            if chosen is not None:
                opts["impersonate"] = chosen
        except Exception:
            pass

    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path

    if cookie_file and os.path.isfile(cookie_file):
        opts["cookiefile"] = cookie_file
    elif cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser, None, None)

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]

    return opts


def probe(url: str, cookie_file: Optional[str] = None,
          cookies_from_browser: Optional[str] = None) -> Dict[str, Any]:
    """仅获取视频元信息，不下载。"""
    opts = build_ydl_opts(
        save_dir=".",
        quality="best",
        download_mode="video",
        cookie_file=cookie_file,
        cookies_from_browser=cookies_from_browser,
        quiet=True,
        platform=detect_platform(url),
    )
    opts["skip_download"] = True

    target_url = normalize_url(url)
    platform = detect_platform(url)
    errors = []
    for attempt in range(4):
        if attempt > 0:
            time.sleep(2.0)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
            return info
        except yt_dlp.utils.DownloadError as e:
            err_str = str(e)
            errors.append(err_str)
            if "No video formats found" in err_str:
                raise
            if "412" in err_str or "Precondition Failed" in err_str:
                continue
            friendly = friendly_error(err_str, platform)
            if friendly:
                raise yt_dlp.utils.DownloadError(friendly)
            raise
    raise yt_dlp.utils.DownloadError(
        f"下载失败，已重试 {len(errors)} 次，最后一次错误: {errors[-1] if errors else '未知'}"
    )


def get_formats(url: str, cookie_file: Optional[str] = None,
                cookies_from_browser: Optional[str] = None) -> List[Dict[str, Any]]:
    info = probe(url, cookie_file, cookies_from_browser)
    return info.get("formats", []) or []


def download(
    url: str,
    save_dir: str,
    quality: str = "best",
    download_mode: str = "video",
    cookie_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
    ffmpeg_path: Optional[str] = None,
    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """下载主入口。返回 yt-dlp 的 info dict。"""
    opts = build_ydl_opts(
        save_dir=save_dir,
        quality=quality,
        download_mode=download_mode,
        cookie_file=cookie_file,
        cookies_from_browser=cookies_from_browser,
        ffmpeg_path=ffmpeg_path or find_ffmpeg(),
        progress_hook=progress_hook,
        quiet=True,
        platform=detect_platform(url),
    )
    target = normalize_url(url)
    platform = detect_platform(url)
    errors = []
    for attempt in range(3):
        if attempt > 0:
            time.sleep(2.5)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=True)
            return info
        except yt_dlp.utils.DownloadError as e:
            err_str = str(e)
            errors.append(err_str)
            if "412" in err_str or "Precondition Failed" in err_str:
                continue
            if "No video formats" in err_str:
                raise
            friendly = friendly_error(err_str, platform)
            if friendly:
                raise yt_dlp.utils.DownloadError(friendly)
            raise
    raise yt_dlp.utils.DownloadError(
        f"下载失败，已重试 {len(errors)} 次: {errors[-1] if errors else '未知'}"
    )


# -------------------- CLI --------------------
def _cli_progress(d: Dict[str, Any]) -> None:
    status = d.get("status")
    if status == "downloading":
        pct = d.get("_percent_str", "").strip()
        speed = d.get("_speed_str", "").strip()
        eta = d.get("_eta_str", "").strip()
        sys.stdout.write(f"\r  下载中 {pct}  速度 {speed}  剩余 {eta}   ")
        sys.stdout.flush()
    elif status == "finished":
        sys.stdout.write("\n  合并中...\n")
        sys.stdout.flush()
    elif status == "error":
        sys.stdout.write(f"\n  错误: {d.get('error')}\n")


def main_cli() -> int:
    print("=" * 60)
    print(" B站 / 小红书 / 抖音 视频下载器 (CLI)")
    print(" 依赖: yt-dlp   ffmpeg(可选,用于合并音视频)")
    print("=" * 60)
    if len(sys.argv) < 2:
        print("用法: python downloader.py <URL或BV号> [保存目录] [清晰度]")
        print("  清晰度可选: best / 1080 / 720 / 480 / 360 / 240")
        print("示例: python downloader.py BV1xx411c7mD ./downloads 1080")
        return 1
    url = sys.argv[1]
    save_dir = sys.argv[2] if len(sys.argv) > 2 else "./downloads"
    quality = sys.argv[3] if len(sys.argv) > 3 else "best"
    print(f"链接: {normalize_url(url)}")
    print(f"保存: {save_dir}")
    print(f"清晰度: {quality}")
    try:
        info = download(
            url=url,
            save_dir=save_dir,
            quality=quality,
            progress_hook=_cli_progress,
        )
        print(f"\n完成 -> {info.get('_filename') or info.get('title')}")
        return 0
    except Exception as e:
        print(f"\n下载失败: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main_cli())
