# -*- coding: utf-8 -*-
"""stegpy(stegv3) 提取测试。

测试里自带一个与 stegpy 官方 encode_message 完全对应的嵌入器，
用来验证提取端（尤其是“有密码”这条路径——原脚本在这条路上必然误报密码错误）。
"""

from __future__ import annotations

import base64
import os

import numpy as np
import pytest
from PIL import Image

from strike import stegpy_extract
from strike.errors import StrikeError


def _encrypt(password: str, payload: bytes) -> bytes:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    return salt + Fernet(key).encrypt(payload)


def _encode_message(host: np.ndarray, message: bytes, bits: int) -> np.ndarray:
    """与 stegpy.lsb.encode_message 一致。"""
    shape = host.shape
    flat = host.reshape(-1)
    divisor = 8 // bits
    if flat.size % divisor:
        flat = np.resize(flat, flat.size + (divisor - flat.size % divisor))

    msg = np.zeros(len(flat) // divisor, dtype=np.uint8)
    msg[: len(message)] = list(message)

    flat[: divisor * len(message)] &= 256 - 2**bits
    for index in range(divisor):
        flat[index::divisor] |= msg >> bits * index & (2**bits - 1)

    operand = 0 if bits == 1 else (16 if bits == 2 else 32)
    flat[0] = (flat[0] & 207) | operand
    return flat.reshape(shape)


def embed(
    host_path,
    out_path,
    payload: bytes,
    *,
    filename: str | None = None,
    password: str | None = None,
    bits: int = 2,
) -> None:
    message = b"stegv3" + len(payload).to_bytes(4, "big")
    if filename:
        name = filename.encode("utf-8")
        message += len(name).to_bytes(1, "big") + name
    else:
        message += (0).to_bytes(1, "big")
    message += payload
    if password:
        message = _encrypt(password, message)

    with Image.open(host_path) as img:
        host = np.array(img.convert("RGB"))
    Image.fromarray(_encode_message(host, message, bits)).save(out_path)


@pytest.fixture()
def host(tmp_path):
    rng = np.random.default_rng(2024)
    array = rng.integers(60, 200, size=(120, 120, 3), dtype=np.uint8)
    path = tmp_path / "host.png"
    Image.fromarray(array).save(path)
    return path


def test_extract_text(tmp_path, host, imgs_dir):
    marked = tmp_path / "marked.png"
    embed(host, marked, "flag{stegpy_text}".encode())
    text, produced = stegpy_extract.extract(marked)
    assert text == "flag{stegpy_text}"
    assert produced is None


@pytest.mark.parametrize("bits", [1, 2, 4])
def test_extract_text_with_all_bit_depths(tmp_path, host, imgs_dir, bits):
    marked = tmp_path / "marked.png"
    embed(host, marked, b"hello", bits=bits)
    text, _ = stegpy_extract.extract(marked)
    assert text == "hello"


def test_extract_file_payload(tmp_path, host, imgs_dir):
    marked = tmp_path / "marked.png"
    embed(host, marked, b"\x89PNG fake bytes", filename="secret.bin")
    text, produced = stegpy_extract.extract(marked)
    assert produced is not None
    assert produced.read_bytes() == b"\x89PNG fake bytes"
    assert produced.parent == imgs_dir / "stegpy_out"
    assert "secret.bin" in text


def test_extract_with_password(tmp_path, host, imgs_dir):
    """原脚本在这条路径上一定失败（把整段填充当成 Fernet token）。"""
    marked = tmp_path / "marked.png"
    embed(host, marked, b"flag{with_password}", password="p@ssw0rd")
    text, _ = stegpy_extract.extract(marked, "p@ssw0rd")
    assert text == "flag{with_password}"


def test_extract_wrong_password(tmp_path, host, imgs_dir):
    marked = tmp_path / "marked.png"
    embed(host, marked, b"flag{x}", password="right")
    with pytest.raises(StrikeError, match="密码错误"):
        stegpy_extract.extract(marked, "wrong")


def test_missing_password_reports_no_magic(tmp_path, host, imgs_dir):
    marked = tmp_path / "marked.png"
    embed(host, marked, b"flag{x}", password="right")
    with pytest.raises(StrikeError, match="没有找到 stegpy"):
        stegpy_extract.extract(marked)


def test_clean_image_reports_no_hidden_data(tmp_path, host, imgs_dir):
    with pytest.raises(StrikeError, match="没有找到 stegpy"):
        stegpy_extract.extract(host)


def test_jpeg_is_rejected_with_hint(tmp_path):
    path = tmp_path / "pic.jpg"
    Image.new("RGB", (40, 40), "red").save(path, "JPEG")
    with pytest.raises(StrikeError, match="JPEG"):
        stegpy_extract.extract(path)


def test_chinese_filename_payload(tmp_path, host, imgs_dir):
    marked = tmp_path / "marked.png"
    embed(host, marked, b"data", filename="中文文件.txt")
    _, produced = stegpy_extract.extract(marked)
    assert produced is not None and produced.name == "中文文件.txt"
