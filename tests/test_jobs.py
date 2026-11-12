# -*- coding: utf-8 -*-
"""调度层测试：界面点 Pwn 之后真正发生的事。"""

from __future__ import annotations

import shutil
import zlib

import numpy as np
import pytest
from PIL import Image

from strike import jobs, paths, stegtools
from strike.errors import StrikeError


def _tamper_png(path, out, size):
    raw = bytearray(path.read_bytes())
    pos = raw.find(b"IHDR") - 4
    width, height = size
    raw[pos + 8 : pos + 16] = width.to_bytes(4, "big") + height.to_bytes(4, "big")
    out.write_bytes(raw)
    return out


def run(index, img1="", img2=""):
    lines: list[str] = []
    result = jobs.run_job(index, img1, img2, log=lines.append)
    return result, lines


def test_modes_are_consistent():
    assert [mode.index for mode in jobs.MODES] == list(range(len(jobs.MODES)))
    labels = [mode.label for mode in jobs.MODES]
    assert len(set(labels)) == len(labels)
    assert all(mode.hint for mode in jobs.MODES)


def test_unknown_index_raises():
    with pytest.raises(StrikeError, match="未知的隐写方式"):
        jobs.run_job(99, "x")


def test_missing_img1_is_reported():
    result, lines = run(4, "")
    assert result.ok is False
    assert any("Img1 文件路径为空" in line for line in lines)


def test_watermark_mode(tmp_path, imgs_dir):
    cover = np.random.default_rng(3).integers(0, 256, (16, 16), dtype=np.uint8)
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.fromarray(cover).save(a)
    Image.fromarray(np.clip(cover.astype(int) + 4, 0, 255).astype(np.uint8)).save(b)

    for index, name in ((1, "result1.png"), (2, "result2.png")):
        result, lines = run(index, str(a), str(b))
        assert result.ok, lines
        assert result.preview == imgs_dir / name
        assert result.preview.exists()


def test_watermark_needs_img2(tmp_path, imgs_dir, make_png):
    result, lines = run(2, str(make_png()))
    assert result.ok is False
    assert any("Img2 文件路径为空" in line for line in lines)


def test_qrcode_mode(imgs_dir, make_qr):
    result, lines = run(3, str(make_qr("flag{qr_job}")))
    assert result.ok, lines
    assert any("flag{qr_job}" in line for line in lines)


def test_qrcode_mode_without_code(imgs_dir, make_png):
    result, lines = run(3, str(make_png()))
    assert result.ok is False
    assert any("未识别到二维码" in line for line in lines)


def test_invert_mode(imgs_dir, make_png):
    result, lines = run(4, str(make_png()))
    assert result.ok, lines
    assert result.preview.name == "result4.png"
    assert result.preview.exists()


def test_rgb_mode(tmp_path, imgs_dir):
    txt = tmp_path / "rgb.txt"
    txt.write_text("\n".join(["1 2 3"] * 16), encoding="utf-8")
    result, lines = run(5, str(txt))
    assert result.ok, lines
    assert result.preview.name == "result5.png"
    assert result.preview.exists()


def test_png_fix_mode(tmp_path, imgs_dir, make_png):
    original = make_png(size=(320, 200))
    broken = _tamper_png(original, tmp_path / "broken.png", (16, 16))
    result, lines = run(6, str(broken))
    assert result.ok, lines
    assert result.preview.name == "result6.png"
    assert Image.open(result.preview).size == (320, 200)


def test_png_check_mode(imgs_dir, make_png):
    if not paths.tool("pngcheck", "pngcheck.exe").exists():
        pytest.skip("缺少 tools/pngcheck")
    result, lines = run(7, str(make_png()))
    assert result.ok, lines
    assert any("IHDR" in line for line in lines)


def test_metadata_mode(imgs_dir, make_png):
    result, lines = run(8, str(make_png()))
    assert result.ok, lines
    assert any("基本信息" in line for line in lines)


def test_gif_mode(imgs_dir, make_gif):
    result, lines = run(9, str(make_gif(frames=3)))
    assert result.ok, lines
    assert result.preview and result.preview.name == "frame1.png"


@pytest.mark.skipif(shutil.which("java") is None, reason="缺少 java")
def test_f5_mode_reports_negative(imgs_dir, make_jpeg):
    result, lines = run(10, str(make_jpeg()))
    assert result.ok is False
    assert any("F5" in line for line in lines)


def test_strings_mode(tmp_path, imgs_dir):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"\x00flag{strings_job}\x00")
    result, lines = run(11, str(blob))
    assert result.ok, lines
    assert any("flag{strings_job}" in line for line in lines)
    assert any(line.startswith("0x") for line in lines)


@pytest.mark.parametrize("index, name", [(12, "result12.jpg"), (13, "result13.jpg")])
def test_jpg_fix_modes(tmp_path, imgs_dir, make_jpeg, index, name):
    original = make_jpeg(size=(320, 200))
    raw = bytearray(original.read_bytes())
    from strike import dimfix

    pos = dimfix._find_sof(raw)
    raw[pos + 5 : pos + 7] = (100).to_bytes(2, "big")  # 高度砍半
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(raw)

    result, lines = run(index, str(broken))
    assert result.ok, lines
    assert result.preview.name == name
    assert result.preview.exists()


def test_bin2img_mode(tmp_path, imgs_dir):
    txt = tmp_path / "bits.txt"
    txt.write_text("1001", encoding="utf-8")
    result, lines = run(14, str(txt))
    assert result.ok, lines
    assert result.preview.name == "result14.png"


def test_stegpy_mode_negative(imgs_dir, make_png):
    result, lines = run(15, str(make_png()))
    assert result.ok is False
    assert any("stegpy" in line for line in lines)


@pytest.mark.skipif(not paths.tool("steghide", "steghide.exe").exists(), reason="缺少 steghide")
def test_steghide_mode_negative(imgs_dir, make_jpeg):
    result, lines = run(16, str(make_jpeg(size=(64, 64))))
    assert result.ok is False
    assert any("未能提取出内容" in line for line in lines)


@pytest.mark.skipif(
    not paths.tool("foremost", "foremost.exe").exists(), reason="缺少 foremost"
)
def test_foremost_mode(tmp_path, imgs_dir, make_jpeg):
    jpeg = make_jpeg(size=(160, 120))
    blob = tmp_path / "carve.bin"
    blob.write_bytes(b"\x00" * 2048 + jpeg.read_bytes() + b"\x00" * 2048)
    result, lines = run(17, str(blob))
    assert result.ok, lines
    assert result.extra["out_dir"].exists()
    assert any("foremost 恢复出" in line for line in lines)


def test_all_in_one_mode(imgs_dir, make_png):
    result, lines = run(0, str(make_png()))
    assert any("基本信息" in line for line in lines)
    assert any("巡检结论" in line for line in lines)
    assert isinstance(result.ok, bool)


def test_unexpected_exception_is_caught(monkeypatch, imgs_dir, make_png):
    """单项异常不能把整个界面带崩。"""

    def boom(*_args, **_kwargs):
        raise RuntimeError("模拟内部错误")

    monkeypatch.setattr(jobs.imageops, "invert", boom)
    result, lines = run(4, str(make_png()))
    assert result.ok is False
    assert any("未捕获的异常" in line for line in lines)
