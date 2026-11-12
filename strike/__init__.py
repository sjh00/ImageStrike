# -*- coding: utf-8 -*-
"""ImageStrike 的核心实现。

本包不依赖 PyQt5，可直接在命令行/脚本中调用，方便单测与批处理。
"""

from __future__ import annotations

__version__ = "0.3.0"

from .errors import StrikeError  # noqa: F401

__all__ = ["__version__", "StrikeError"]
