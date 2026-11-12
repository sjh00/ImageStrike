# -*- coding: utf-8 -*-
"""统一的异常类型。"""

from __future__ import annotations


class StrikeError(Exception):
    """可预期的业务错误，消息会原样展示给用户。"""


class ToolMissingError(StrikeError):
    """外部程序（java / pngcheck / steghide / foremost）不可用。"""
