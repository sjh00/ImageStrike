# -*- coding: utf-8 -*-
"""纯像素运算类功能：反相、RGB 转图、01 转黑白图、GIF 拆帧。"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

from .errors import StrikeError

_NUMBER_SPLIT = re.compile(r"[\s,]+")


def _open(path: Path | str) -> Image.Image:
    path = Path(path)
    if not path.exists():
        raise StrikeError(f"文件不存在：{path}")
    try:
        return Image.open(path)
    except OSError as exc:
        raise StrikeError(f"无法识别的图片格式：{path.name}（{exc}）") from exc


def invert(path: Path | str, out_file: Path | str) -> Path:
    """图片反相，保留 alpha 通道。"""
    with _open(path) as img:
        has_alpha = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        )
        converted = img.convert("RGBA" if has_alpha else "RGB")
        array = np.asarray(converted, dtype=np.uint8)

    if has_alpha:
        array = array.copy()
        array[..., :3] = 255 - array[..., :3]
    else:
        array = 255 - array

    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(out_file, "PNG")
    return out_file


def _guess_shape(count: int) -> tuple[int, int]:
    """由数据量推断 (宽, 高)：优先完全平方，否则取最接近正方形的因子对。"""
    if count <= 0:
        raise StrikeError("文件里没有有效数据")
    side = math.isqrt(count)
    if side * side == count:
        return side, side
    best = None
    for width in range(1, side + 1):
        if count % width:
            continue
        height = count // width
        if best is None or abs(width - height) < abs(best[0] - best[1]):
            best = (width, height)
    if best is None:
        raise StrikeError(f"共 {count} 个像素点，无法分解为矩形，请检查输入数据")
    return best


def rgb_to_image(txt_path: Path | str, out_file: Path | str, *, log=None) -> tuple[int, int]:
    """每行 “R G B” 的文本转图片，返回 (宽, 高)。"""
    txt_path = Path(txt_path)
    if not txt_path.exists():
        raise StrikeError(f"文件不存在：{txt_path}")

    pixels: list[tuple[int, int, int]] = []
    bad_lines = 0
    with txt_path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            parts = _NUMBER_SPLIT.split(line)
            if len(parts) < 3:
                bad_lines += 1
                continue
            try:
                pixels.append((int(parts[0]), int(parts[1]), int(parts[2])))
            except ValueError:
                bad_lines += 1

    if not pixels:
        raise StrikeError("没有解析到任何 RGB 数据，请确认每行格式为 “R G B”")

    array = np.array(pixels, dtype=np.uint8)
    width, height = _guess_shape(len(pixels))
    if width * height != len(pixels):
        raise StrikeError(f"共 {len(pixels)} 个像素点，无法拼成 {width}x{height}")

    image = array.reshape(height, width, 3)
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    # 用 PNG 而不是原脚本的 JPG：隐写题的颜色值必须无损
    Image.fromarray(image).save(out_file, "PNG")

    if log:
        log(f"[*] 共 {len(pixels)} 个像素，输出尺寸 {width}x{height}")
        if width != height:
            log("[!] 行数不是完全平方数，已按最接近正方形的因子对推断尺寸")
        if bad_lines:
            log(f"[!] 跳过 {bad_lines} 行无法解析的数据")
    return width, height


def binary_to_image(txt_path: Path | str, out_file: Path | str, *, log=None) -> tuple[int, int]:
    """0/1 文本转黑白矩阵图，返回 (宽, 高)。"""
    txt_path = Path(txt_path)
    if not txt_path.exists():
        raise StrikeError(f"文件不存在：{txt_path}")

    text = txt_path.read_text(encoding="utf-8", errors="replace")
    bits = [ch for ch in text if ch in "01"]
    visible = len(re.sub(r"\s", "", text))
    ignored = max(visible - len(bits), 0)
    if not bits:
        raise StrikeError("没有找到 0/1 数据，请确认文件内容")

    width, height = _guess_shape(len(bits))
    if width * height != len(bits):
        raise StrikeError(f"共 {len(bits)} 个 0/1，无法拼成 {width}x{height}")

    values = np.frombuffer("".join(bits).encode("ascii"), dtype=np.uint8) - ord("0")
    # 1 -> 黑，0 -> 白（与原脚本一致）
    array = np.where(values.reshape(height, width) == 1, 0, 255).astype(np.uint8)

    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(out_file, "PNG")

    if log:
        log(f"[*] 共 {len(bits)} 个 0/1，输出尺寸 {width}x{height}")
        if width != height:
            log("[!] 数据量不是完全平方数，已按最接近正方形的因子对推断尺寸")
        if ignored:
            log(f"[!] 忽略 {ignored} 个非 0/1 字符")
    return width, height


def split_gif(path: Path | str, out_dir: Path | str, *, log=None) -> list[Path]:
    """GIF 拆帧，输出到 out_dir，返回生成的文件列表。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("frame*.png"):
        stale.unlink()

    saved: list[Path] = []
    with _open(path) as img:
        total = getattr(img, "n_frames", 1)
        if total <= 1:
            raise StrikeError("这是单帧图片，没有可拆分的帧")
        keep_alpha = "transparency" in img.info
        for index in range(total):
            img.seek(index)
            frame = img.convert("RGBA" if keep_alpha else "RGB")
            target = out_dir / f"frame{index + 1}.png"
            frame.save(target, "PNG")
            frame.close()
            saved.append(target)

    if log:
        log(f"[*] 共拆出 {len(saved)} 帧，目录：{out_dir}")
    return saved
