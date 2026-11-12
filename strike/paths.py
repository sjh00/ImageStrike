# -*- coding: utf-8 -*-
"""路径约定：所有输出都落在程序目录下，不依赖当前工作目录。"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
IMGS_DIR = BASE_DIR / "imgs"
TOOLS_DIR = BASE_DIR / "tools"


def ensure_imgs() -> Path:
    IMGS_DIR.mkdir(parents=True, exist_ok=True)
    return IMGS_DIR


def out_path(name: str) -> Path:
    """imgs/ 下的输出文件路径。"""
    return ensure_imgs() / name


def out_dir(name: str) -> Path:
    """imgs/ 下的输出子目录（已创建）。"""
    path = ensure_imgs() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def tool(*parts: str) -> Path:
    """tools/ 下的外部程序路径。"""
    return TOOLS_DIR.joinpath(*parts)
