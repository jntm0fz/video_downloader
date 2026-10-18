@echo off
chcp 65001 >nul
title B站视频下载器
cd /d "%~dp0"

REM 优先用同目录的 python,否则用 PATH 里的
set PY=python
where python >nul 2>&1
if errorlevel 1 set PY=py

"%PY%" gui.py %*
if errorlevel 1 pause
