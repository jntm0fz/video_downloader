import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

APP_VERSION = "1.1.0"
CONFIG_NAME = "update_config.json"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return app_dir() / CONFIG_NAME


def load_config() -> Dict[str, str]:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return {"repository": str(data.get("repository", "")).strip()}
    except (OSError, ValueError, TypeError):
        return {"repository": ""}


def save_repository(repository: str) -> None:
    config_path().write_text(
        json.dumps({"repository": repository.strip()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_version(value: str) -> Tuple[int, ...]:
    numbers = re.findall(r"\d+", value.lstrip("vV"))
    return tuple(int(n) for n in numbers[:4]) or (0,)


def is_newer(remote: str, local: str = APP_VERSION) -> bool:
    return parse_version(remote) > parse_version(local)


def release_url(repository: str) -> str:
    return f"https://api.github.com/repos/{repository.strip('/')}/releases/latest"


def current_exe_name() -> str:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().name
    return ""


def select_asset(assets: list[dict], platform_name: str = "windows", exe_name: Optional[str] = None) -> Optional[dict]:
    name_of_self = exe_name if exe_name is not None else current_exe_name()
    is_lite = ("轻量" in name_of_self) or ("lite" in name_of_self.lower())
    if is_lite:
        preferred = ("B站视频下载器-轻量版.exe", "B站视频下载器.exe", "downloader.exe", "video-downloader.exe")
    else:
        preferred = ("B站视频下载器.exe", "B站视频下载器-轻量版.exe", "downloader.exe", "video-downloader.exe")
    for name in preferred:
        for asset in assets:
            if asset.get("name", "").lower() == name.lower():
                return asset
    for asset in assets:
        name = asset.get("name", "").lower()
        if platform_name == "windows" and name.endswith(".exe"):
            return asset
    return None


def check_update(repository: Optional[str] = None) -> Optional[dict]:
    repo = (repository or load_config()["repository"]).strip("/")
    if not repo:
        return None
    request = urllib.request.Request(
        release_url(repo),
        headers={"Accept": "application/vnd.github+json", "User-Agent": "VideoDownloader"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    tag = str(data.get("tag_name", ""))
    if not tag or not is_newer(tag):
        return None
    asset = select_asset(data.get("assets", []))
    if not asset:
        return None
    return {
        "tag": tag,
        "name": data.get("name") or tag,
        "url": asset["browser_download_url"],
        "asset_name": asset["name"],
        "size": asset.get("size", 0),
    }


def download_update(info: dict, progress: Optional[Callable[[int, int], None]] = None) -> Path:
    destination = app_dir() / f"{info['asset_name']}.new"
    request = urllib.request.Request(
        info["url"],
        headers={"Accept": "application/octet-stream", "User-Agent": "VideoDownloader"},
    )
    with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length") or info.get("size") or 0)
        received = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            received += len(chunk)
            if progress:
                progress(received, total)
    return destination


def schedule_replace(new_file: Path, current_file: Optional[Path] = None) -> None:
    if getattr(sys, "frozen", False):
        current_file = current_file or Path(sys.executable).resolve()
    else:
        current_file = current_file or Path(sys.argv[0]).resolve()
    command_file = app_dir() / "apply_video_downloader_update.cmd"
    target = current_file
    command = (
        "@echo off\r\n"
        f":wait\r\n"
        f'tasklist /fi "PID eq {os.getpid()}" | find "{os.getpid()}" >nul\r\n'
        f"if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\r\n"
        f'move /y "{new_file}" "{target}" >nul\r\n'
        f'del /q "{command_file}" >nul 2>nul\r\n'
    )
    command_file.write_text(command, encoding="mbcs", errors="replace")
    subprocess.Popen(["cmd.exe", "/c", str(command_file)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def install_update(info: dict, progress: Optional[Callable[[int, int], None]] = None) -> Path:
    new_file = download_update(info, progress)
    if not new_file.exists() or new_file.stat().st_size == 0:
        raise RuntimeError("更新文件下载失败")
    schedule_replace(new_file)
    return new_file
