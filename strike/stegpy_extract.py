# -*- coding: utf-8 -*-
"""stegpy（stegv3 格式）提取。

按 stegpy 官方实现（stegpy/lsb.py、crypt.py）重写，修掉原脚本的三处问题：
1. wav/gif 分支没有 `header, data = content`，直接抛 NameError；
2. 有密码时 `Fernet.decrypt(msg[16:])` 把整段填充数据当成 token，
   导致明明密码正确也报“密码错误”——改为试探合法 token 边界；
3. 提取出的文件被写成 “_文件名” 丢在当前目录，现在放到 imgs/stegpy_out/。

不支持：JPEG（新版 stegpy 把数据藏在 DCT 系数里，需要 jpeglib），
遇到时会给出明确提示而不是静默失败。
"""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
from PIL import Image

from . import paths
from .errors import StrikeError

MAGIC = b"stegv3"
_B64_CHARS = frozenset(
    b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_="
)
_JPEG_SUFFIXES = {".jpg", ".jpeg", ".jfif"}


def _open_gif(path: Path):
    """尽量按“保留调色板索引”的方式读 GIF，与 stegpy 的取数方式一致。"""
    from PIL import GifImagePlugin

    strategy = getattr(GifImagePlugin, "LoadingStrategy", None)
    previous = getattr(GifImagePlugin, "LOADING_STRATEGY", None)
    if strategy is not None and hasattr(strategy, "RGB_AFTER_DIFFERENT_PALETTE_ONLY"):
        GifImagePlugin.LOADING_STRATEGY = strategy.RGB_AFTER_DIFFERENT_PALETTE_ONLY
    try:
        image = Image.open(path)
        frames = []
        try:
            while True:
                frames.append(np.array(image))
                image.seek(image.tell() + 1)
        except EOFError:
            pass
        return frames
    finally:
        if previous is not None:
            GifImagePlugin.LOADING_STRATEGY = previous


def _content(path: Path) -> np.ndarray:
    """复刻 stegpy 的取数方式，返回待解调的像素/采样数组。"""
    suffix = path.suffix.lower()

    if suffix in _JPEG_SUFFIXES:
        raise StrikeError(
            "暂不支持 JPEG 的 stegpy 数据：新版 stegpy 把内容藏在 DCT 系数里，"
            "需要 jpeglib 才能读取，请改用官方 stegpy 命令行处理"
        )

    if suffix == ".wav":
        raw = np.fromfile(path, dtype=np.uint8)
        if raw.size <= 10000:
            raise StrikeError("wav 文件太小，不足以容纳隐写数据")
        return raw[10000:]  # 前 10000 字节是 wav 头，stegpy 不写入

    if suffix == ".gif":
        frames = _open_gif(path)
        if not frames:
            raise StrikeError("gif 中没有可用的帧")
        return np.asarray(frames)

    with Image.open(path) as image:
        if image.mode != "RGB":
            image = image.convert("RGB")
        return np.array(image)


def _demodulate(data: np.ndarray) -> np.ndarray:
    """把嵌入位还原成字节流（与 stegpy.decode_message 完全一致）。"""
    flat = data.reshape(-1)
    if flat.size == 0:
        raise StrikeError("文件里没有可用的像素数据")

    bits = 2 ** int((int(flat[0]) & 48) >> 4)  # 第 5、6 位记录每字节用几个比特
    divisor = 8 // bits
    if divisor <= 0:
        raise StrikeError("图片头部标记异常，可能不是 stegpy 隐写")

    if flat.size % divisor:
        flat = np.resize(flat, flat.size + (divisor - flat.size % divisor))

    msg = np.zeros(flat.size // divisor, dtype=np.uint8)
    for index in range(divisor):
        msg |= (flat[index::divisor] & (2**bits - 1)) << (bits * index)
    return msg


def _token_lengths(token: bytes) -> list[int]:
    """Fernet token 的候选长度：先到第一个非 base64 字符，再按 4 的倍数试探。"""
    max_end = 0
    for byte in token:
        if byte not in _B64_CHARS:
            break
        max_end += 1

    candidates: list[int] = []
    pad = token.find(b"=")
    if pad != -1:
        end = pad + 1
        while end < len(token) and token[end] == ord("="):
            end += 1
        if end <= max_end:
            candidates.append(end)

    candidates.extend(end for end in range(4, max_end + 1) if end % 4 == 0)
    candidates.append(len(token))
    return list(dict.fromkeys(candidates))


def _decrypt(msg: np.ndarray, password: str) -> np.ndarray:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt = bytes(msg[:16])
    token = bytes(msg[16:])
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    fernet = Fernet(key)

    for end in _token_lengths(token):
        try:
            return np.frombuffer(fernet.decrypt(token[:end]), dtype=np.uint8)
        except (InvalidToken, ValueError, TypeError):
            continue
    raise StrikeError("密码错误，无法解密 stegpy 隐写内容")


def _unique_target(out_dir: Path, name: str) -> Path:
    target = out_dir / name
    counter = 1
    while target.exists():
        target = out_dir / f"{Path(name).stem}_{counter}{Path(name).suffix}"
        counter += 1
    return target


def extract(
    path: Path | str, password: str | None = None, *, log=None
) -> tuple[str, Path | None]:
    """提取 stegv3 隐写内容，返回 (文本结果, 落地文件路径或 None)。"""
    path = Path(path)
    if not path.exists():
        raise StrikeError(f"文件不存在：{path}")

    msg = _demodulate(_content(path))
    if password:
        msg = _decrypt(msg, password)

    if bytes(msg[:6]) != MAGIC:
        raise StrikeError(
            "没有找到 stegpy(stegv3) 隐写数据"
            + ("，请确认文件或密码是否正确" if password else "")
        )

    msg_len = int.from_bytes(bytes(msg[6:10]), "big")
    name_len = int.from_bytes(bytes(msg[10:11]), "big")
    body_start = 11 + name_len
    body_end = body_start + msg_len
    if body_end > msg.size:
        raise StrikeError("stegpy 数据长度字段异常，文件可能被截断")

    out_dir = paths.out_dir("stegpy_out")

    if name_len == 0:
        payload = bytes(msg[body_start:body_end])
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            target = _unique_target(out_dir, "message.bin")
            target.write_bytes(payload)
            return "隐写内容不是文本，已保存为二进制文件", target
        preview = text if len(text) <= 200 else text[:200] + "…"
        if log:
            log(f"[*] 隐写文本共 {len(text)} 字符：{preview}")
        return text, None

    original_name = bytes(msg[11:body_start]).decode("utf-8", "replace")
    safe_name = Path(original_name).name or "stegpy_output.bin"
    target = _unique_target(out_dir, safe_name)
    target.write_bytes(bytes(msg[body_start:body_end]))

    if log:
        log(f"[+] 已从 {path.name} 提取出 {original_name}")
    return f"从 {path.name} 中提取出文件：{original_name}", target
