#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ImageStrike - CTF 图片隐写综合利用工具（入口）。

用法：
    uv run python ImageStrike.py                 # 图形界面
    uv run python ImageStrike.py --cli 6 a.png   # 命令行模式
    uv run python ImageStrike.py --list          # 列出全部隐写方式编号
"""

from __future__ import annotations

import sys

from strike import paths, __version__
from strike.errors import StrikeError
from strike.jobs import MODES, run_job

APP_VERSION = f"V{__version__}"


def _cli(argv: list[str]) -> int:
    if "--list" in argv:
        for mode in MODES:
            print(f"{mode.index:>2}  {mode.label}")
        return 0

    args = [item for item in argv if item != "--cli"]
    if not args:
        print("用法：python ImageStrike.py --cli <编号> <Img1> [Img2]")
        print("提示：python ImageStrike.py --list 查看全部编号")
        return 2

    try:
        index = int(args[0])
    except ValueError:
        print(f"[!] 编号必须是数字，收到：{args[0]}")
        return 2

    img1 = args[1] if len(args) > 1 else ""
    img2 = args[2] if len(args) > 2 else ""

    try:
        result = run_job(index, img1, img2, log=lambda line: print(line, flush=True))
    except StrikeError as exc:
        print(f"[!] {exc}")
        return 2
    if result.preview:
        print(f"[*] 结果文件：{result.preview}")
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    paths.ensure_imgs()

    if "--cli" in argv or "--list" in argv:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return _cli(argv)

    try:
        from gui import run_gui
    except ImportError as exc:
        print(f"[!] 缺少界面依赖：{exc}")
        print("   请执行：uv sync")
        return 1

    try:
        return run_gui([sys.argv[0], *argv])
    except StrikeError as exc:
        print(f"[!] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
