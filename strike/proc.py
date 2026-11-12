# -*- coding: utf-8 -*-
"""外部程序调用的公共封装。

替换原先 `subprocess.run('... {}'.format(path), shell=True)` 的写法：
- 参数以列表传递，路径含空格/中文/引号都不会被 shell 拆坏；
- GUI 下不再弹出黑色控制台窗口；
- 统一编码回退（UTF-8 -> GBK -> Latin-1）。
"""

from __future__ import annotations

import os
import subprocess
import shutil
from pathlib import Path

from .errors import ToolMissingError

IS_WINDOWS = os.name == "nt"
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW


def which(program: str) -> str | None:
    """查找可执行文件；tools/ 下的程序直接按路径判断。"""
    if os.path.isabs(program) or os.sep in program or (os.altsep and os.altsep in program):
        return program if Path(program).exists() else None
    return shutil.which(program)


def decode(data: bytes) -> str:
    """把外部程序输出解码成文本，容忍各种历史编码。"""
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def run(
    argv: list[str],
    *,
    cwd: Path | str | None = None,
    timeout: int = 180,
    check_tool: bool = True,
) -> subprocess.CompletedProcess:
    """执行外部命令，返回 CompletedProcess（stdout/stderr 为 bytes）。"""
    if check_tool and not which(argv[0]):
        raise ToolMissingError(f"找不到外部程序：{argv[0]}，请检查环境或 tools 目录")

    try:
        return subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolMissingError(f"'{argv[0]}' 执行超时（>{timeout}s）") from exc
    except FileNotFoundError as exc:
        raise ToolMissingError(f"找不到外部程序：{argv[0]}") from exc


def output_text(result: subprocess.CompletedProcess) -> str:
    """取 stdout，为空时退化为 stderr。"""
    return decode(result.stdout) if result.stdout else decode(result.stderr)
