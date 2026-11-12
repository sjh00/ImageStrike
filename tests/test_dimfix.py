# -*- coding: utf-8 -*-
"""宽高修复：PNG 的 CRC 爆破与 JPEG 的 SOF 改写。"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

from strike import dimfix
from strike.errors import StrikeError


def tamper_png_size(
    path: Path, out: Path, size: tuple[int, int], *, fix_crc: bool = True
) -> Path:
    """把 IHDR 的宽高改成 size（模拟 CTF 里的改宽高题）。

    fix_crc=True 时同时重算 CRC（现代题目常见，CRC 爆破会失效）。
    """
    raw = bytearray(path.read_bytes())
    pos = raw.find(b"IHDR") - 4
    assert pos > 0 and bytes(raw[:8]) == dimfix.PNG_SIGNATURE
    width, height = size
    raw[pos + 8 : pos + 16] = width.to_bytes(4, "big") + height.to_bytes(4, "big")
    if fix_crc:
        crc = zlib.crc32(bytes(raw[pos + 4 : pos + 21]))
        raw[pos + 21 : pos + 25] = crc.to_bytes(4, "big")
    out.write_bytes(raw)
    return out


def tamper_jpeg_size(path: Path, out: Path, axis: str, factor: float = 0.5) -> Path:
    """把 SOF 里的高或宽改小，模拟 CTF 的 jpg 改宽高。"""
    raw = bytearray(path.read_bytes())
    pos = dimfix._find_sof(raw)
    width = int.from_bytes(raw[pos + 7 : pos + 9], "big")
    height = int.from_bytes(raw[pos + 5 : pos + 7], "big")
    if axis == "h":
        height = max(1, int(height * factor))
    else:
        width = max(1, int(width * factor))
    raw[pos + 5 : pos + 7] = height.to_bytes(2, "big")
    raw[pos + 7 : pos + 9] = width.to_bytes(2, "big")
    out.write_bytes(raw)
    return out


def test_png_size_read(make_png):
    path = make_png(size=(320, 200))
    assert dimfix.png_size(path) == (320, 200)


def test_png_crc_bruteforce_when_crc_broken(tmp_path, make_png):
    """改宽高但没重算 CRC：CRC 爆破给出唯一解。"""
    original = make_png(size=(320, 200))
    broken = tamper_png_size(
        original, tmp_path / "broken.png", (16, 16), fix_crc=False
    )
    assert dimfix.png_size(broken) == (16, 16)

    target = tmp_path / "fixed.png"
    assert dimfix.fix_png_size(broken, target, max_side=1024) == (320, 200)
    assert dimfix.png_size(target) == (320, 200)
    with Image.open(target) as img:
        img.load()
        assert img.size == (320, 200)


def test_png_idat_inference_when_crc_recomputed(tmp_path, make_png):
    """改宽高并重算了 CRC：CRC 爆破失效，改用 IDAT 解压长度推断。

    这种情形的候选尺寸天然可能不唯一，工具要把候选全部列出来，
    并且支持用 target_size 精确指定。
    """
    original = make_png(size=(320, 200))
    broken = tamper_png_size(original, tmp_path / "broken.png", (16, 16), fix_crc=True)

    lines: list[str] = []
    target = tmp_path / "fixed.png"
    dimfix.fix_png_size(broken, target, max_side=1024, log=lines.append)
    assert any("IDAT" in line for line in lines)
    assert any("320x200" in line for line in lines), "候选列表里必须出现真实尺寸"

    precise = tmp_path / "precise.png"
    assert dimfix.fix_png_size(
        broken, precise, max_side=1024, target_size=(320, 200)
    ) == (320, 200)
    assert dimfix.png_size(precise) == (320, 200)
    with Image.open(precise) as img:
        img.load()
        assert img.size == (320, 200)


def test_png_idat_rejects_impossible_target(tmp_path, make_png):
    original = make_png(size=(320, 200))
    broken = tamper_png_size(original, tmp_path / "broken.png", (16, 16), fix_crc=True)
    with pytest.raises(StrikeError, match="与数据长度不符"):
        dimfix.fix_png_size(
            broken, tmp_path / "out.png", target_size=(999, 7)
        )


def test_png_reports_when_not_tampered(make_png):
    path = make_png(size=(64, 48))
    with pytest.raises(StrikeError, match="未被篡改"):
        dimfix.fix_png_size(path, path.parent / "out.png")


def test_png_crc_rejects_invalid_signature(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a png at all")
    with pytest.raises(StrikeError, match="PNG"):
        dimfix.fix_png_size(bad, tmp_path / "out.png")


def test_png_crc_limit_message(tmp_path, make_png):
    original = make_png(size=(320, 200))
    broken = tamper_png_size(original, tmp_path / "broken.png", (300, 180), fix_crc=False)
    with pytest.raises(StrikeError, match="没有找到匹配的宽高"):
        dimfix.fix_png_size(broken, tmp_path / "out.png", max_side=64)


def test_png_crc_progress_callback(tmp_path, make_png):
    original = make_png(size=(320, 200))
    broken = tamper_png_size(original, tmp_path / "broken.png", (32, 32), fix_crc=False)
    lines: list[str] = []
    dimfix.fix_png_size(broken, tmp_path / "out.png", max_side=1024, log=lines.append)
    assert any("CRC 匹配成功" in line for line in lines)


def test_jpeg_size_read(make_jpeg):
    path = make_jpeg(size=(320, 200))
    assert dimfix.jpeg_size(path) == (320, 200)


@pytest.mark.parametrize("axis", ["h", "w"])
def test_jpeg_double_restores_size(tmp_path, make_jpeg, axis):
    original = make_jpeg(size=(320, 200))
    broken = tamper_jpeg_size(original, tmp_path / "broken.jpg", axis)

    fixed = tmp_path / f"fixed_{axis}.jpg"
    width, height = dimfix.fix_jpeg_size(broken, fixed, axis=axis)
    expected = (320, 200)  # 无论改的是宽还是高，翻倍后都回到原始尺寸
    assert (width, height) == expected
    with Image.open(fixed) as img:
        assert img.size == expected


def test_jpeg_sof_found_after_exif_segment(tmp_path):
    """带 APP1(EXIF) 段的 JPEG 也能正确定位 SOF。"""
    from PIL import Image as PILImage

    path = tmp_path / "exif.jpg"
    image = PILImage.new("RGB", (120, 90), "red")
    exif = image.getexif()
    exif[0x010E] = "ImageStrike test"
    image.save(path, exif=exif)
    assert dimfix.jpeg_size(path) == (120, 90)


def test_jpeg_invalid_signature(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"\x00" * 32)
    with pytest.raises(StrikeError, match="JPEG"):
        dimfix.fix_jpeg_size(bad, tmp_path / "out.jpg")


def test_jpeg_axis_validation(make_jpeg):
    path = make_jpeg()
    with pytest.raises(ValueError):
        dimfix.fix_jpeg_size(path, path.parent / "o.jpg", axis="x")
