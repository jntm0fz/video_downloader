# -*- mode: python ; coding: utf-8 -*-
import sys, os

block_cipher = None

hiddenimports = [
    'yt_dlp',
    'yt_dlp.utils',
    'yt_dlp.extractor',
    'yt_dlp.extractor.common',
    'yt_dlp.extractor.bilibili',
    'yt_dlp.extractor.tiktok',
    'yt_dlp.extractor.xiaohongshu',
    'yt_dlp.compat',
    'yt_dlp.cookies',
    'yt_dlp.options',
    'yt_dlp.postprocessor',
    'yt_dlp.downloader',
    'yt_dlp.downloader.http',
    'yt_dlp.networking',
    'yt_dlp.networking._requests',
    'yt_dlp.networking._helper',
    'yt_dlp.networking.common',
    'yt_dlp.networking.websocket',
    'yt_dlp.options',
    'yt_dlp.cookies',
    'yt_dlp.postprocessor.ffmpeg',
    'yt_dlp.postprocessor.common',
    'yt_dlp.downloader.common',
    'yt_dlp.downloader.http',
    'yt_dlp.downloader.fragment',
    'yt_dlp.downloader.dash',
    'yt_dlp.downloader.hls',
    'yt_dlp.downloader.external',
    'yt_dlp.downloader.external_ffmpeg',
    'yt_dlp.jsinterp',
    'yt_dlp.socks',
    'yt_dlp.utils',
    'yt_dlp.utils._legacy',
    'yt_dlp.utils._deprecated',
    'yt_dlp.compat._legacy',
    'yt_dlp.compat._deprecated',
    'yt_dlp.compat',
    'yt_dlp.minicurses',
    'yt_dlp.update',
    'yt_dlp.version',
    'tqdm',
    'tqdm.std',
    'tqdm.gui',
    'tqdm.auto',
    'requests',
    'requests.utils',
    'requests.structures',
    'requests.cookies',
    'requests.exceptions',
    'urllib3',
    'urllib3.util',
    'urllib3.response',
    'urllib3.exceptions',
    'urllib3.poolmanager',
    'urllib3.connectionpool',
    'charset_normalizer',
    'idna',
    'certifi',
    'brotli',
    'mutagen',
    'secretstorage',
    'curl_cffi',
    'cchardet',
    'orjson',
    'updater',
    'cookies_tool',
]

datas = [
    (os.path.abspath('downloader.py'), '.'),
]

LITE = os.environ.get('BILIBILI_LITE', '') == '1'

binaries = []

if not LITE:
    try:
        import shutil, tempfile
        import imageio_ffmpeg
        _ffmpeg_src = imageio_ffmpeg.get_ffmpeg_exe()
        if _ffmpeg_src and os.path.isfile(_ffmpeg_src):
            _ffmpeg_dir = os.path.join(tempfile.gettempdir(), 'bilibili_ffmpeg_build')
            os.makedirs(_ffmpeg_dir, exist_ok=True)
            _ffmpeg_dst = os.path.join(_ffmpeg_dir, 'ffmpeg.exe')
            if not os.path.isfile(_ffmpeg_dst) or os.path.getsize(_ffmpeg_dst) != os.path.getsize(_ffmpeg_src):
                shutil.copy2(_ffmpeg_src, _ffmpeg_dst)
            binaries.append((_ffmpeg_dst, '.'))
    except Exception:
        pass

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'PIL', 'cv2',
        'pyqt', 'PyQt', 'PySide', 'PyQt5', 'PyQt6',
        'imageio_ffmpeg',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='video-downloader-lite' if LITE else 'video-downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    onefile=True,
    runtime_tmpdir=None,
)
