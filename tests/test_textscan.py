# -*- coding: utf-8 -*-
"""可打印字符串提取测试。"""

from __future__ import annotations

import pytest

from strike.errors import StrikeError
from strike.textscan import extract_strings


def test_offsets_and_order(tmp_path):
    path = tmp_path / "blob.bin"
    payload = b"\x00\x01flag{abc}\x00\x02hello_world\x00\xff"
    path.write_bytes(payload)

    hits, total = extract_strings(path)
    texts = [text for _, text in hits]
    assert "flag{abc}" in texts
    assert "hello_world" in texts
    assert total == len(hits)

    offsets = dict(hits)
    assert next(o for o, t in hits if t == "flag{abc}") == payload.index(b"flag{abc}")
    assert offsets.values()


def test_min_length(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"abc\x00abcdef\x00")
    short, _ = extract_strings(path, min_length=3)
    assert any(text == "abc" for _, text in short)
    long, _ = extract_strings(path, min_length=6)
    assert all(len(text) >= 6 for _, text in long)


def test_utf16_detection(tmp_path):
    """UTF-16LE 的宽字符字符串（Windows 程序里常见）。"""
    path = tmp_path / "wide.bin"
    payload = "flag{wide_string}".encode("utf-16-le")
    path.write_bytes(b"\x00\x00" + payload + b"\x00\x00")
    hits, _ = extract_strings(path)
    texts = [text for _, text in hits]
    assert any("flag{wide_string}" in text for text in texts)
    assert any(offset == 2 for offset, _ in hits)


def test_utf16_can_be_disabled(tmp_path):
    path = tmp_path / "wide.bin"
    path.write_bytes("plaintext".encode("utf-16-le"))
    hits, _ = extract_strings(path, include_utf16=False)
    assert hits == []


def test_limit_and_total(tmp_path):
    path = tmp_path / "many.bin"
    path.write_bytes(b"\x00".join(b"string%d" % i for i in range(50)))
    hits, total = extract_strings(path, limit=10)
    assert len(hits) == 10
    assert total >= 50


def test_empty_file(tmp_path):
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")
    with pytest.raises(StrikeError, match="为空"):
        extract_strings(path)


def test_missing_file(tmp_path):
    with pytest.raises(StrikeError, match="文件不存在"):
        extract_strings(tmp_path / "nope.bin")
