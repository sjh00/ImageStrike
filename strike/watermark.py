# -*- coding: utf-8 -*-
"""盲水印（FFT 差值法）。

算法取自 chishaxie/blindwatermark 的早期实现：两张同尺寸图片做二维 FFT 相减、
除以 alpha 取实部，得到差值图，差值图本身就是“隐藏的水印”。

与原脚本的差异（都是为了让它在新环境下跑得起来，灰度图结果逐字节一致）：
1. `random.shuffle(x, random=random.random)` 的 `random` 参数在 Python 3.11 被删除，
   这里按 3.10 及更早版本的分支逻辑重新实现（`_shuffle_legacy`）；
2. `np.uint8(负数)` 在 NumPy 2 会抛 OverflowError，改成等价的
   “截断取整后取低 8 位”（与原 C 转换语义一致）；
3. 原脚本用 `cv2.imdecode(..., IMREAD_UNCHANGED)` 读取，灰度图得到二维数组可以正常
   计算，而彩色图得到三维数组时 `np.uint8(rwm[i][j])` 会直接抛异常——也就是说原版
   实际只支持灰度图。这里对彩色图按通道并行做同样的置换，输出彩色差值图。
"""

from __future__ import annotations

import random
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from .errors import StrikeError

SEED = 20160930
ALPHA = 3.0

_GRAY_MODES = {"1", "L", "LA", "I", "I;16", "I;16B", "I;16L", "F"}
_JPEG_SUFFIXES = {".jpg", ".jpeg", ".jfif"}

_seed_lock = threading.Lock()


def read_native(path: Path | str) -> np.ndarray:
    """读取图片，保持原始通道数。

    - 灰度图 -> 二维数组（与原脚本 IMREAD_UNCHANGED 的行为一致，也是本算法真正有效的场景）；
    - 彩色图 -> (h, w, C) 三维数组；
    - JPEG 按 cv2 的 BGR 顺序返回，方便与既有脚本对比。
    """
    path = Path(path)
    try:
        with Image.open(path) as img:
            if img.mode in _GRAY_MODES:
                array = np.asarray(img.convert("L"), dtype=np.uint8)
            elif img.mode in ("RGBA", "LA", "P", "PA"):
                array = np.asarray(img.convert("RGBA"), dtype=np.uint8)
            else:
                array = np.asarray(img.convert("RGB"), dtype=np.uint8)
    except FileNotFoundError as exc:
        raise StrikeError(f"文件不存在：{path}") from exc
    except OSError as exc:
        raise StrikeError(f"无法识别的图片格式：{path.name}（{exc}）") from exc

    if path.suffix.lower() in _JPEG_SUFFIXES and array.ndim == 3:
        array = array[:, :, ::-1]  # RGB -> BGR，与 cv2.imread 一致
    return np.ascontiguousarray(array)


def _to_uint8_like_c(values: np.ndarray) -> np.ndarray:
    """等价于原脚本的 `np.uint8(v)`：截断取整后取低 8 位。"""
    return (np.trunc(values).astype(np.int64) & 0xFF).astype(np.uint8)


def _shuffle_legacy(items: list[int], rand=random.random) -> None:
    """复刻 `random.shuffle(items, random=rand)`（Python 3.10 及以前的实现）。"""
    for i in reversed(range(1, len(items))):
        j = int(rand() * (i + 1))
        items[i], items[j] = items[j], items[i]


def _permutations(shape: tuple[int, ...], seed: int, oldseed: bool):
    """按种子生成行/列置换表。

    oldseed=True 走旧的（Python2 兼容）分支，对应界面上的“[01] 盲水印（旧版种子）”。
    """
    with _seed_lock:
        rows = list(range(int(shape[0] * 0.5)))
        cols = list(range(shape[1]))
        if oldseed:
            random.seed(seed, version=1)  # version=1：Py2/Py3 得到相同序列
            _shuffle_legacy(rows, random.random)
            _shuffle_legacy(cols, random.random)
        else:
            random.seed(seed)
            random.shuffle(rows)
            random.shuffle(cols)
    return rows, cols


def embed(
    cover_path: Path | str,
    marked_path: Path | str,
    out_file: Path | str,
    *,
    oldseed: bool = False,
    alpha: float = ALPHA,
    seed: int = SEED,
    log=None,
) -> Path:
    """计算两张图片的 FFT 差值图并保存。"""
    cover = read_native(cover_path)
    marked = read_native(marked_path)

    if cover.shape != marked.shape:
        raise StrikeError(
            "两张图片尺寸/通道不一致，无法做差值："
            f"Img1={_describe(cover.shape)}，Img2={_describe(marked.shape)}"
        )

    rows, cols = _permutations(cover.shape, seed, oldseed)

    diff = np.real((np.fft.fft2(marked) - np.fft.fft2(cover)) / alpha)

    height, width = diff.shape[0], diff.shape[1]
    half = int(height * 0.5)

    result = np.zeros(diff.shape, dtype=np.uint8)
    # 前一半的行按置换表打散，列同样打散
    result[np.ix_(rows, cols)] = _to_uint8_like_c(diff[:half])
    # 后一半上下左右翻转填充，保证频谱共轭对称
    result[height - half : height] = result[0:half][::-1, ::-1]

    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    _save(result, out_file)
    if log:
        log(f"[*] 差值图已生成：{out_file}（{_describe(cover.shape)}）")
    return out_file


def _describe(shape: tuple[int, ...]) -> str:
    if len(shape) == 2:
        return f"{shape[1]}x{shape[0]} 灰度"
    return f"{shape[1]}x{shape[0]} {shape[2]}通道"


def _save(array: np.ndarray, path: Path) -> None:
    image = Image.fromarray(array)
    if path.suffix.lower() in _JPEG_SUFFIXES:
        image.convert("RGB").save(path, "JPEG", quality=100)
    else:
        image.save(path)
