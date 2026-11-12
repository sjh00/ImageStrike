# -*- coding: utf-8 -*-
"""外部工具封装测试（pngcheck / steghide / foremost / F5）。

这些用例依赖仓库自带的 tools/ 目录；缺少对应程序时自动跳过，
不会把“环境没装”伪装成“代码有错”。
"""

from __future__ import annotations

import shutil

import pytest

from strike import paths, stegtools
from strike.errors import StrikeError
from strike.proc import decode, run

PNGCHECK = paths.tool("pngcheck", "pngcheck.exe")
STEGHIDE = paths.tool("steghide", "steghide.exe")
FOREMOST = paths.tool("foremost", "foremost.exe")
JAVA = shutil.which("java")

needs_pngcheck = pytest.mark.skipif(not PNGCHECK.exists(), reason="缺少 tools/pngcheck")
needs_steghide = pytest.mark.skipif(not STEGHIDE.exists(), reason="缺少 tools/steghide")
needs_foremost = pytest.mark.skipif(not FOREMOST.exists(), reason="缺少 tools/foremost")
needs_java = pytest.mark.skipif(
    not JAVA or not paths.tool("F5", "Extract.class").exists(), reason="缺少 java 或 tools/F5"
)


@needs_pngcheck
def test_pngcheck_valid_file(make_png):
    text = stegtools.pngcheck(make_png(size=(32, 24)))
    assert "IHDR" in text
    assert "CRC error" not in text


@needs_pngcheck
def test_pngcheck_reports_damage(tmp_path, make_png):
    broken = tmp_path / "broken.png"
    broken.write_bytes(make_png(size=(32, 24)).read_bytes()[:-20])
    text = stegtools.pngcheck(broken)
    assert text.strip()


@needs_pngcheck
def test_pngcheck_missing_file(tmp_path):
    with pytest.raises(StrikeError, match="文件不存在"):
        stegtools.pngcheck(tmp_path / "nope.png")


@needs_steghide
def test_steghide_roundtrip_with_password(tmp_path, make_jpeg, imgs_dir):
    cover = make_jpeg(size=(320, 200))
    secret = tmp_path / "secret.txt"
    secret.write_text("flag{steghide_ok}", encoding="utf-8")
    stego = tmp_path / "stego.jpg"

    embed = run(
        [
            str(STEGHIDE),
            "embed",
            "-cf",
            str(cover),
            "-ef",
            str(secret),
            "-p",
            "p@ss",
            "-sf",
            str(stego),
        ],
        cwd=tmp_path,
        timeout=120,
    )
    assert stego.exists(), decode(embed.stdout) + decode(embed.stderr)

    ok, text, produced = stegtools.steghide_extract(stego, "p@ss")
    assert ok, text
    assert produced
    assert produced[0].read_bytes() == secret.read_bytes()
    assert produced[0].parent == imgs_dir / "steghide_out"


@needs_steghide
def test_steghide_tries_empty_password(tmp_path, make_jpeg, imgs_dir):
    cover = make_jpeg(size=(320, 200))
    secret = tmp_path / "secret.txt"
    secret.write_text("flag{no_password}", encoding="utf-8")
    stego = tmp_path / "stego.jpg"

    embed = run(
        [
            str(STEGHIDE),
            "embed",
            "-cf",
            str(cover),
            "-ef",
            str(secret),
            "-p",
            "",  # 空口令
            "-sf",
            str(stego),
        ],
        cwd=tmp_path,
        timeout=120,
    )
    assert stego.exists(), decode(embed.stdout) + decode(embed.stderr)

    ok, text, produced = stegtools.steghide_extract(stego, None)
    assert ok, text
    assert produced and produced[0].read_bytes() == secret.read_bytes()


@needs_steghide
def test_steghide_wrong_password_fails(make_jpeg, imgs_dir):
    cover = make_jpeg(size=(64, 64))
    ok, text, produced = stegtools.steghide_extract(cover, "wrong")
    assert ok is False
    assert produced == []
    assert "尝试" in text


@needs_foremost
def test_foremost_carves_embedded_jpeg(tmp_path, make_jpeg, imgs_dir):
    """把一张 jpg 埋进垃圾数据里，foremost 必须能把它挖出来。

    这条同时验证了三件事：配置文件能找到、-T 不能加、-q 不能加。
    """
    jpeg = make_jpeg(size=(160, 120))
    blob = tmp_path / "carve.bin"
    blob.write_bytes(b"\x00" * 2048 + jpeg.read_bytes() + b"\x00" * 2048)

    ok, text, out_dir = stegtools.foremost(blob)
    assert ok, text
    carved = [
        item
        for item in out_dir.rglob("*")
        if item.is_file() and item.name not in ("audit.txt", "progress.log")
    ]
    assert carved, "foremost 没有恢复出任何文件"
    assert any(item.suffix == ".jpg" for item in carved)


@needs_java
def test_f5_reports_not_f5_for_plain_jpeg(make_jpeg):
    status, text = stegtools.f5_extract(make_jpeg(size=(320, 200)))
    assert status in {"not_f5", "error"}, text


@needs_java
def test_f5_does_not_touch_repo_output(make_jpeg, imgs_dir):
    """仓库自带 tools/F5/output.txt，提取结果不能写回那里。"""
    shipped = paths.tool("F5", "output.txt")
    before = shipped.read_bytes() if shipped.exists() else None
    status, _ = stegtools.f5_extract(make_jpeg(size=(64, 64)))
    assert status != "ok"
    after = shipped.read_bytes() if shipped.exists() else None
    assert before == after


def test_missing_tool_error_message(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TOOLS_DIR", tmp_path / "notools")
    with pytest.raises(StrikeError, match="缺少外部程序"):
        stegtools.pngcheck(tmp_path / "a.png")
