# -*- coding: utf-8 -*-
"""图片宽高被篡改后的恢复。

- PNG：IHDR 里保留了原始 CRC，暴力枚举宽高直到 CRC 匹配；
- JPEG：直接定位 SOF 段改写宽高字段（原脚本用“整文件转 hex 再做字符串替换”，
  既可能替换到别处的字节，也不支持非 2 倍场景）。
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from PIL import Image

from .errors import StrikeError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# SOF0~SOF15 中真正携带尺寸的那些（排除 DHT/JPG/DAC）
_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


def _read(path: Path | str) -> bytearray:
    path = Path(path)
    try:
        return bytearray(path.read_bytes())
    except FileNotFoundError as exc:
        raise StrikeError(f"文件不存在：{path}") from exc


def png_size(path: Path | str) -> tuple[int, int]:
    raw = _read(path)
    pos, length = _find_ihdr(raw)
    return (
        int.from_bytes(raw[pos + 8 : pos + 12], "big"),
        int.from_bytes(raw[pos + 12 : pos + 16], "big"),
    )


def _find_ihdr(raw: bytearray) -> tuple[int, int]:
    """返回 (IHDR chunk 起始偏移, 块数据长度)。"""
    if bytes(raw[:8]) != PNG_SIGNATURE:
        raise StrikeError("不是合法的 PNG 文件（文件头不匹配）")
    pos = 8
    while pos + 8 <= len(raw):
        length = int.from_bytes(raw[pos : pos + 4], "big")
        chunk_type = bytes(raw[pos + 4 : pos + 8])
        if chunk_type == b"IHDR":
            if length != 13:
                raise StrikeError("IHDR 数据块长度异常，文件可能已损坏")
            return pos, length
        pos += 12 + length
    raise StrikeError("未找到 IHDR 数据块，文件可能已损坏")


_CHANNELS_BY_COLOR_TYPE = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _png_idat_stream(raw: bytearray) -> bytes:
    """拼接所有 IDAT 块的数据。"""
    pos = 8
    parts: list[bytes] = []
    while pos + 8 <= len(raw):
        length = int.from_bytes(raw[pos : pos + 4], "big")
        chunk_type = bytes(raw[pos + 4 : pos + 8])
        if chunk_type == b"IDAT":
            parts.append(bytes(raw[pos + 8 : pos + 8 + length]))
        elif chunk_type == b"IEND":
            break
        pos += 12 + length
    return b"".join(parts)


def _expected_raw_size(width: int, height: int, bit_depth: int, color_type: int) -> int:
    """非隔行 PNG 解压后的原始数据长度。"""
    channels = _CHANNELS_BY_COLOR_TYPE.get(color_type, 0)
    row_bytes = (width * bit_depth * channels + 7) // 8
    return height * (row_bytes + 1)


def _candidates_from_idat(
    raw: bytearray, bit_depth: int, color_type: int, max_side: int
) -> tuple[list[tuple[int, int]], int, bytes]:
    """按 IDAT 解压长度反推可能的 (宽, 高)。

    针对“改宽高的同时把 CRC 也算对了”的题目：此时 CRC 爆破失效，
    但像素数据长度仍然对应真实尺寸。
    """
    channels = _CHANNELS_BY_COLOR_TYPE.get(color_type, 0)
    if not channels:
        return [], 0, b""
    try:
        data = zlib.decompress(_png_idat_stream(raw))
    except zlib.error:
        return [], 0, b""
    raw_size = len(data)
    if raw_size == 0:
        return [], 0, b""

    bits_per_pixel = bit_depth * channels
    candidates: list[tuple[int, int]] = []
    for width in range(1, max_side + 1):
        divisor = (width * bits_per_pixel + 7) // 8 + 1
        if raw_size % divisor:
            continue
        candidates.append((width, raw_size // divisor))
    return candidates, raw_size, data


def _filter_bytes_valid(
    data: bytes, width: int, height: int, bit_depth: int, color_type: int
) -> bool:
    """校验每条扫描线的首字节（filter type）是否都在 0~4。

    尺寸猜错时步长就错了，取到的位置基本是随机像素值，
    一个真实尺寸通常只有 5/256 的概率“碰巧”通过单行检查，多行几乎不可能。
    """
    channels = _CHANNELS_BY_COLOR_TYPE.get(color_type, 0)
    if not channels or height <= 0:
        return False
    step = (width * bit_depth * channels + 7) // 8 + 1
    if step * height != len(data):
        return False
    for offset in range(0, len(data), step):
        if data[offset] > 4:
            return False
    return True


def fix_png_size(
    path: Path | str,
    out_file: Path | str,
    *,
    max_side: int = 4096,
    target_size: tuple[int, int] | None = None,
    log=None,
) -> tuple[int, int]:
    """还原被篡改的 PNG 宽高，返回 (宽, 高)。

    两条路径：
    1. IHDR 的 CRC 与数据不符（改宽高没重算 CRC）——枚举宽高直到 CRC 命中，结果唯一；
    2. CRC 校验通过但 IDAT 数据长度与声明尺寸不符（改宽高并重算了 CRC）——
       按解压长度反推候选尺寸。这种情况天然可能有多个解，会把全部候选打印出来，
       默认取“行首 filter 字节合法 + 面积最大”的一个；猜错时用 target_size 指定。
    """
    raw = _read(path)
    pos, _ = _find_ihdr(raw)

    width = int.from_bytes(raw[pos + 8 : pos + 12], "big")
    height = int.from_bytes(raw[pos + 12 : pos + 16], "big")
    # IHDR 的 CRC 覆盖 “类型 + 13 字节数据”
    target_crc = int.from_bytes(raw[pos + 21 : pos + 25], "big")
    body = bytes(raw[pos + 4 : pos + 21])
    bit_depth = raw[pos + 16]
    color_type = raw[pos + 17]
    interlace = raw[pos + 20]

    if zlib.crc32(body) != target_crc:
        width, height = _brute_force_by_crc(raw, pos, target_crc, max_side, log)
        # CRC 命中时原来的 CRC 值依然有效，可以直接沿用
        raw[pos + 8 : pos + 16] = width.to_bytes(4, "big") + height.to_bytes(4, "big")
        reason = "CRC 匹配成功"
    else:
        if log:
            log(f"[*] 当前宽高 {width}x{height} 的 CRC 校验通过（题目可能重算了 CRC）")
        if interlace:
            raise StrikeError("当前图片是隔行扫描（Adam7），无法按数据长度推断宽高")
        expected = _expected_raw_size(width, height, bit_depth, color_type)
        candidates, raw_size, data = _candidates_from_idat(
            raw, bit_depth, color_type, max_side
        )
        if not candidates:
            raise StrikeError("无法从 IDAT 数据长度推断宽高，文件可能已损坏")
        if log:
            log(f"[*] IDAT 解压后 {raw_size} 字节，声明尺寸对应应为 {expected} 字节")
        if raw_size == expected:
            raise StrikeError(
                f"当前宽高 {width}x{height} 与 CRC 校验、数据长度均一致，未被篡改，无需修复"
            )

        if target_size:
            if target_size not in candidates:
                preview = "、".join(f"{w}x{h}" for w, h in candidates)
                raise StrikeError(
                    f"指定的尺寸 {target_size[0]}x{target_size[1]} 与数据长度不符，可用候选：{preview}"
                )
            candidates = [target_size]
        else:
            plausible = [
                (w, h)
                for w, h in candidates
                if _filter_bytes_valid(data, w, h, bit_depth, color_type)
            ]
            if plausible:
                candidates = plausible
            candidates.sort(key=lambda item: item[0] * item[1], reverse=True)
            if log:
                preview = "、".join(f"{w}x{h}" for w, h in candidates)
                log(f"[*] 由数据长度反推出的候选尺寸：{preview}")
                if len(candidates) > 1:
                    log(f"[!] 候选不唯一，默认取 {candidates[0][0]}x{candidates[0][1]}，"
                        "若结果不对请用 target_size 指定其它候选")

        width, height = candidates[0]
        raw[pos + 8 : pos + 16] = width.to_bytes(4, "big") + height.to_bytes(4, "big")
        new_crc = zlib.crc32(bytes(raw[pos + 4 : pos + 21]))
        raw[pos + 21 : pos + 25] = new_crc.to_bytes(4, "big")
        reason = "按 IDAT 数据长度反推"

    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_bytes(raw)

    if log:
        log(f"[+] {reason}，还原宽高为 {width}x{height}")
        _verify(out_file, log)
    return width, height


def _brute_force_by_crc(
    raw: bytearray, pos: int, target_crc: int, max_side: int, log
) -> tuple[int, int]:
    """枚举宽高直到 IHDR 的 CRC 命中。"""
    if log:
        declared = (
            int.from_bytes(raw[pos + 8 : pos + 12], "big"),
            int.from_bytes(raw[pos + 12 : pos + 16], "big"),
        )
        log(f"[*] 当前宽高 {declared[0]}x{declared[1]} 的 CRC 校验失败，开始枚举（上限 {max_side}）…")

    middle = bytes(raw[pos + 16 : pos + 21])  # 位深/颜色类型/压缩/滤波/隔行
    crc32 = zlib.crc32
    head = bytearray(b"IHDR\x00\x00\x00\x00")
    tails = [h.to_bytes(4, "big") + middle for h in range(1, max_side + 1)]

    for w in range(1, max_side + 1):
        struct.pack_into(">I", head, 4, w)
        prefix_crc = crc32(head)
        for idx, tail in enumerate(tails, 1):
            if crc32(tail, prefix_crc) == target_crc:
                return w, idx
        if log and w % 512 == 0:
            log(f"[*] 已枚举宽度 {w}/{max_side} …")

    raise StrikeError(f"在 1~{max_side} 范围内没有找到匹配的宽高，可提高上限后重试")


def jpeg_size(path: Path | str) -> tuple[int, int]:
    """读取 JPEG 的 (宽, 高)。"""
    raw = _read(path)
    pos = _find_sof(raw)
    height = int.from_bytes(raw[pos + 5 : pos + 7], "big")
    width = int.from_bytes(raw[pos + 7 : pos + 9], "big")
    return width, height


def _find_sof(raw: bytearray) -> int:
    if bytes(raw[:2]) != b"\xff\xd8":
        raise StrikeError("不是合法的 JPEG 文件（文件头不匹配）")
    pos = 2
    while pos + 4 <= len(raw):
        if raw[pos] != 0xFF:
            pos += 1
            continue
        marker = raw[pos + 1]
        if marker == 0xFF:  # 填充字节
            pos += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:  # 无长度字段
            pos += 2
            continue
        length = int.from_bytes(raw[pos + 2 : pos + 4], "big")
        if marker in _SOF_MARKERS:
            return pos
        if length < 2:
            break
        pos += 2 + length
    raise StrikeError("未找到 SOF 段，可能不是完整的 JPEG 文件")


def fix_jpeg_size(
    path: Path | str,
    out_file: Path | str,
    *,
    axis: str = "h",
    scale: int = 2,
    log=None,
) -> tuple[int, int]:
    """把 JPEG 的宽或高放大 scale 倍，返回新的 (宽, 高)。"""
    if axis not in ("h", "w"):
        raise ValueError("axis 只能是 'h' 或 'w'")
    raw = _read(path)
    pos = _find_sof(raw)
    height = int.from_bytes(raw[pos + 5 : pos + 7], "big")
    width = int.from_bytes(raw[pos + 7 : pos + 9], "big")
    if width == 0 or height == 0:
        raise StrikeError("SOF 段中的宽高为 0，文件可能已损坏")

    new_width, new_height = width, height
    if axis == "h":
        new_height = min(height * scale, 0xFFFF)
    else:
        new_width = min(width * scale, 0xFFFF)

    raw[pos + 5 : pos + 7] = new_height.to_bytes(2, "big")
    raw[pos + 7 : pos + 9] = new_width.to_bytes(2, "big")

    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_bytes(raw)

    if log:
        log(f"[+] 原尺寸 {width}x{height} -> {new_width}x{new_height}")
        _verify(out_file, log)
    return new_width, new_height


def _verify(path: Path, log) -> None:
    """用 Pillow 复核一次，失败只提示不中断。"""
    try:
        with Image.open(path) as img:
            img.load()
            size = img.size
        log(f"[*] 复核通过：Pillow 解析尺寸为 {size[0]}x{size[1]}")
    except Exception as exc:  # noqa: BLE001 - 修复后的文件本就可能不完整
        log(f"[!] 提示：Pillow 无法完整解码（{type(exc).__name__}: {exc}），请用看图软件确认")
