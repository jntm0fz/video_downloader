"""自动获取 cookies：从本机已安装的浏览器里读取并合并成 cookies.txt。"""
import os
import sys
import tempfile
import webbrowser
from typing import Dict, List, Optional, Tuple

try:
    from yt_dlp.cookies import (
        YoutubeDLCookieJar,
        extract_cookies_from_browser,
    )
    HAS_YTDLP_COOKIES = True
except Exception:
    YoutubeDLCookieJar = None
    extract_cookies_from_browser = None
    HAS_YTDLP_COOKIES = False


NATIVE_BROWSERS = [
    "chrome",
    "edge",
    "brave",
    "firefox",
    "chromium",
    "opera",
    "vivaldi",
    "whale",
]

NATIVE_ROOTS: List[Tuple[str, str, List[str]]] = [
    ("Google Chrome", "chrome", [r"%LOCALAPPDATA%\Google\Chrome\User Data"]),
    ("Microsoft Edge", "edge", [r"%LOCALAPPDATA%\Microsoft\Edge\User Data"]),
    ("Brave", "brave", [r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"]),
    ("Mozilla Firefox", "firefox", [r"%APPDATA%\Mozilla\Firefox\Profiles"]),
    ("Chromium", "chromium", [r"%LOCALAPPDATA%\Chromium\User Data"]),
    ("Opera", "opera", [r"%APPDATA%\Opera Software\Opera Stable"]),
    ("Vivaldi", "vivaldi", [r"%LOCALAPPDATA%\Vivaldi\User Data"]),
    ("Naver Whale", "whale", [r"%LOCALAPPDATA%\Naver\Naver Whale\User Data"]),
]

CN_ROOTS: List[Tuple[str, str, List[str]]] = [
    ("360极速浏览器", "chrome", [r"%LOCALAPPDATA%\360Chrome\Chrome\User Data"]),
    ("360安全浏览器", "chrome", [r"%LOCALAPPDATA%\360se6\User Data", r"%APPDATA%\360se6\User Data"]),
    ("QQ浏览器", "chrome", [r"%LOCALAPPDATA%\Tencent\QQBrowser\User Data"]),
    ("搜狗高速浏览器", "chrome", [r"%LOCALAPPDATA%\SogouExplorer\User Data", r"%APPDATA%\SogouExplorer"]),
    ("猎豹浏览器", "chrome", [r"%LOCALAPPDATA%\liebao\User Data"]),
    ("2345加速浏览器", "chrome", [r"%LOCALAPPDATA%\2345Explorer\User Data"]),
    ("UC浏览器", "chrome", [r"%LOCALAPPDATA%\UCBrowser\User Data"]),
]

BROWSER_ROOTS: List[Tuple[str, str, List[str]]] = NATIVE_ROOTS + CN_ROOTS

BROWSER_ORDER = NATIVE_BROWSERS + [name for name, _, _ in CN_ROOTS]

PLATFORM_DOMAINS: Dict[str, List[str]] = {
    "bilibili": ["bilibili.com", "b23.tv"],
    "douyin": ["douyin.com", "iesdouyin.com", "bytedance.com"],
    "xiaohongshu": ["xiaohongshu.com", "xhslink.com"],
    "weibo": ["weibo.com", "weibo.cn", "video.weibo.com"],
    "ixigua": ["ixigua.com", "iesdouyin.com"],
    "acfun": ["acfun.cn"],
}

PLATFORM_NAMES = {
    "bilibili": "B站",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "weibo": "微博",
    "ixigua": "西瓜视频",
    "acfun": "AcFun",
}

PLATFORM_SITES = {
    "bilibili": "https://www.bilibili.com/",
    "douyin": "https://www.douyin.com/",
    "xiaohongshu": "https://www.xiaohongshu.com/",
    "weibo": "https://weibo.com/",
    "ixigua": "https://www.ixigua.com/",
    "acfun": "https://www.acfun.cn/",
}


def domain_matches(host: str, domains: List[str]) -> bool:
    host = (host or "").lstrip(".").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def default_cookie_path() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return os.path.join(base, "cookies_auto.txt")
    except OSError:
        return os.path.join(tempfile.gettempdir(), "cookies_auto.txt")


def _profile_dirs(root: str) -> List[Tuple[str, str]]:
    if not os.path.isdir(root):
        return []
    found: List[Tuple[str, str]] = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    for name in names:
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        if os.path.isfile(os.path.join(path, "Preferences")) or os.path.isdir(
            os.path.join(path, "Network")
        ):
            found.append((name, path))
    return found


def _firefox_ready(root: str) -> bool:
    if not os.path.isdir(root):
        return False
    if os.path.isfile(os.path.join(root, "cookies.sqlite")):
        return True
    try:
        names = os.listdir(root)
    except OSError:
        return False
    return any(os.path.isfile(os.path.join(root, n, "cookies.sqlite")) for n in names)


def detected_browsers() -> List[Tuple[str, str, str]]:
    found: List[Tuple[str, str, str]] = []
    for display, engine, roots in BROWSER_ROOTS:
        profiles: List[Tuple[str, str]] = []
        for raw in roots:
            root = os.path.expandvars(raw)
            if engine == "firefox":
                if _firefox_ready(root):
                    profiles.append((os.path.basename(root.rstrip("\\/")) or display, root))
            else:
                profiles.extend(_profile_dirs(root))
        for profile_name, profile_path in profiles:
            if len(profiles) > 1:
                found.append((f"{display} ({profile_name})", engine, profile_path))
            else:
                found.append((display, engine, profile_path))
    return found


def available_browsers() -> List[Tuple[str, str]]:
    return [(display, path) for display, _, path in detected_browsers()]


def _resolve_browser(browser: str, detected: Optional[List[Tuple[str, str, str]]] = None):
    detected = detected_browsers() if detected is None else detected
    for display, engine, path in detected:
        if browser == display or browser == display.split(" (")[0]:
            return engine, path
    if browser in NATIVE_BROWSERS:
        return browser, None
    return None, None


def read_browser_cookies(browser: str, domains: List[str], detected=None):
    engine, profile = _resolve_browser(browser, detected)
    if engine is None:
        raise RuntimeError("未检测到该浏览器")
    jar = (
        extract_cookies_from_browser(engine, profile)
        if profile
        else extract_cookies_from_browser(engine)
    )
    kept = YoutubeDLCookieJar()
    count = 0
    for cookie in jar:
        if domain_matches(cookie.domain, domains):
            try:
                kept.set_cookie(cookie)
                count += 1
            except Exception:
                pass
    return kept, count


def collect_cookies(
    domains: List[str], browsers: Optional[List[str]] = None
) -> Tuple["YoutubeDLCookieJar", List[Tuple[str, str, int]]]:
    """从多个浏览器读取指定域名的 cookies，返回合并后的 jar 和每个浏览器的结果。"""
    if not HAS_YTDLP_COOKIES:
        raise RuntimeError("当前环境缺少 yt-dlp，无法读取浏览器 cookies。")
    detected = detected_browsers()
    if browsers is None:
        browsers = [display for display, _, _ in detected] or list(BROWSER_ORDER)
    merged = YoutubeDLCookieJar()
    details: List[Tuple[str, str, int]] = []
    for browser in browsers:
        try:
            jar, count = read_browser_cookies(browser, domains, detected)
        except FileNotFoundError:
            details.append((browser, "不可用 (没有 Cookies 数据库)", 0))
            continue
        except PermissionError:
            details.append((browser, "不可用 (数据库被占用，请先关闭浏览器)", 0))
            continue
        except Exception as exc:
            details.append((browser, f"不可用 ({str(exc)[:40]})", 0))
            continue
        for cookie in jar:
            try:
                merged.set_cookie(cookie)
            except Exception:
                pass
        details.append((browser, "已读取", count))
    return merged, details


def save_jar(jar, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    jar.save(out_path, ignore_discard=True, ignore_expires=True)
    return out_path


def auto_get_cookies(
    platforms: List[str],
    out_path: Optional[str] = None,
    browsers: Optional[List[str]] = None,
) -> Dict[str, object]:
    """
    自动从浏览器获取 cookies 并保存为 cookies.txt。
    返回 dict: path / details / found / missing / total
    """
    platforms = [p for p in (platforms or []) if p in PLATFORM_DOMAINS]
    if not platforms:
        platforms = list(PLATFORM_DOMAINS.keys())

    domains: List[str] = []
    for p in platforms:
        domains.extend(PLATFORM_DOMAINS[p])

    jar, details = collect_cookies(domains, browsers)

    found = []
    missing = []
    for p in platforms:
        if any(domain_matches(c.domain, PLATFORM_DOMAINS[p]) for c in jar):
            found.append(p)
        else:
            missing.append(p)

    path = None
    if jar:
        path = save_jar(jar, out_path or default_cookie_path())

    return {
        "path": path,
        "details": details,
        "found": found,
        "missing": missing,
        "total": len(jar),
    }


def open_platform_sites(platforms: List[str]) -> None:
    for p in platforms:
        url = PLATFORM_SITES.get(p)
        if url:
            try:
                webbrowser.open(url)
            except Exception:
                pass
