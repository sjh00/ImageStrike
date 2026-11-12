# -*- coding: utf-8 -*-
"""可打印字符串提取（内置实现，不依赖 strings.exe）。

相比原脚本：
- 直接在 bytes 上匹配，不再把整份二进制 decode 成 utf-8 再正则（原来会丢数据、也慢）；
- 附带文件偏移，方便在十六进制编辑器里定位；
- 同时扫描 UTF-16LE，覆盖 Windows 程序里常见的宽字符字符串。
"""

from __future__ import annotations

import re
from pathlib import Path

from .errors import StrikeError

_CHARSET = rb"A-Za-z0-9/\-:.,_$%'()\[\]<> +*=|{}@#!?~^"


def _ascii_pattern(min_length: int) -> re.Pattern:
    return re.compile(rb"[" + _CHARSET + rb"]{" + str(min_length).encode() + rb",}")


def _utf16_pattern(min_length: int) -> re.Pattern:
    unit = rb"(?:[" + _CHARSET + rb"]\x00)"
    return re.compile(unit + rb"{" + str(min_length).encode() + rb",}")


def _runs(data: bytes, pattern: re.Pattern, encoding: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for match in pattern.finditer(data):
        text = match.group().decode(encoding, "replace").strip()
        if text:
            hits.append((match.start(), text))
    return hits


def extract_strings(
    path: Path | str,
    *,
    min_length: int = 4,
    limit: int = 4000,
    include_utf16: bool = True,
) -> tuple[list[tuple[int, str]], int]:
    """返回 ([(偏移, 字符串)], 总命中数)，按偏移排序。"""
    path = Path(path)
    if not path.exists():
        raise StrikeError(f"文件不存在：{path}")

    data = path.read_bytes()
    if not data:
        raise StrikeError("文件内容为空")

    hits = _runs(data, _ascii_pattern(min_length), "ascii")
    if include_utf16:
        hits.extend(_runs(data, _utf16_pattern(min_length), "utf-16-le"))

    hits.sort(key=lambda item: item[0])
    return hits[:limit], len(hits)
