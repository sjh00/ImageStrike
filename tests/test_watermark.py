# -*- coding: utf-8 -*-
"""盲水印：与旧版算法（Python 3.10 及以前）保持逐字节一致。"""

from __future__ import annotations

import hashlib
import random

import numpy as np
import pytest
from PIL import Image

from strike import watermark
from strike.errors import StrikeError

# 以下期望值由 Python 3.10.15 实跑原始代码得到：
#   random.seed(seed, version=1); random.shuffle(x, random=random.random)
GROUND_TRUTH = {
    False: ([0, 1, 3, 2], [3, 2, 5, 4, 1, 0]),
    True: ([2, 0, 3, 1], [5, 2, 4, 0, 3, 1]),
}
FINGERPRINT = {
    False: "be42e380ac84fbda39c19c91847a6d22",
    True: "ac697ade19392dda6eb67a2028a97da7",
}


def _reference_permutations(shape, seed=watermark.SEED, oldseed=False):
    """按原脚本语义独立复刻一遍置换生成过程。"""
    rows = list(range(int(shape[0] * 0.5)))
    cols = list(range(shape[1]))
    random.seed(seed, version=1) if oldseed else random.seed(seed)
    if oldseed:
        for items in (rows, cols):
            for i in reversed(range(1, len(items))):
                j = int(random.random() * (i + 1))
                items[i], items[j] = items[j], items[i]
    else:
        random.shuffle(rows)
        random.shuffle(cols)
    return rows, cols


def _reference_image(cover: np.ndarray, marked: np.ndarray, rows, cols, alpha=3.0):
    """原脚本的差值图计算，逐行转写（含 2D/3D 两种情形）。"""
    diff = np.real((np.fft.fft2(marked) - np.fft.fft2(cover)) / alpha)
    height, width = diff.shape[0], diff.shape[1]
    result = np.zeros(diff.shape, dtype=np.uint8)
    for i in range(int(height * 0.5)):
        for j in range(width):
            result[rows[i]][cols[j]] = (
                np.trunc(diff[i][j]).astype(np.int64) & 0xFF
            ).astype(np.uint8)
    for i in range(int(height * 0.5)):
        for j in range(width):
            result[height - i - 1][width - j - 1] = result[i][j]
    return result


@pytest.mark.parametrize("oldseed", [False, True])
def test_permutation_matches_python310(oldseed):
    rows, cols = watermark._permutations((8, 6), watermark.SEED, oldseed)
    assert (rows, cols) == GROUND_TRUTH[oldseed]


@pytest.mark.parametrize("oldseed", [False, True])
def test_permutation_fingerprint_matches_python310(oldseed):
    rows, cols = watermark._permutations((256, 320), watermark.SEED, oldseed)
    payload = ",".join(map(str, rows)) + "|" + ",".join(map(str, cols))
    assert hashlib.md5(payload.encode()).hexdigest() == FINGERPRINT[oldseed]


@pytest.mark.parametrize("oldseed", [False, True])
def test_embed_grayscale_matches_reference(tmp_path, oldseed):
    """灰度图是原脚本唯一能跑通的场景，输出必须逐字节一致。"""
    rng = np.random.default_rng(20240808)
    cover = rng.integers(0, 256, size=(24, 32), dtype=np.uint8)
    marked = np.clip(cover.astype(np.int16) + rng.integers(-6, 7, cover.shape), 0, 255)

    cover_path = tmp_path / "cover.png"
    marked_path = tmp_path / "marked.png"
    out_path = tmp_path / "result.png"
    Image.fromarray(cover).save(cover_path)
    Image.fromarray(marked.astype(np.uint8)).save(marked_path)

    watermark.embed(cover_path, marked_path, out_path, oldseed=oldseed)

    rows, cols = _reference_permutations(cover.shape, oldseed=oldseed)
    expected = _reference_image(cover, marked.astype(np.uint8), rows, cols)
    actual = np.asarray(Image.open(out_path))
    np.testing.assert_array_equal(actual, expected)


def test_embed_color_image_does_not_crash(tmp_path):
    """原脚本遇到彩色图会在 np.uint8(向量) 上崩溃，这里要求能正常出图。"""
    rng = np.random.default_rng(11)
    cover = rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
    marked = np.clip(cover.astype(np.int16) + 5, 0, 255).astype(np.uint8)

    cover_path = tmp_path / "c.png"
    marked_path = tmp_path / "m.png"
    out_path = tmp_path / "out.png"
    Image.fromarray(cover).save(cover_path)
    Image.fromarray(marked).save(marked_path)
    watermark.embed(cover_path, marked_path, out_path)

    rows, cols = _reference_permutations(cover.shape)
    expected = _reference_image(cover, marked, rows, cols)
    np.testing.assert_array_equal(np.asarray(Image.open(out_path)), expected)


def test_channel_order_is_native_for_png(tmp_path):
    """PNG 按存储的 RGB 顺序处理（等价 IMREAD_UNCHANGED），不做额外交换。"""
    cover = np.zeros((8, 8, 3), dtype=np.uint8)
    cover[:, :, 0] = 200
    marked = cover.copy()
    marked[:, :, 2] = 120

    Image.fromarray(cover).save(tmp_path / "c.png")
    Image.fromarray(marked).save(tmp_path / "m.png")

    rows, cols = _reference_permutations(cover.shape)
    expected = _reference_image(cover, marked, rows, cols)

    out_path = tmp_path / "out.png"
    watermark.embed(tmp_path / "c.png", tmp_path / "m.png", out_path)
    np.testing.assert_array_equal(np.asarray(Image.open(out_path)), expected)


def test_embed_shape_mismatch_raises(tmp_path):
    Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8)).save(tmp_path / "a.png")
    Image.fromarray(np.zeros((12, 10, 3), dtype=np.uint8)).save(tmp_path / "b.png")
    with pytest.raises(StrikeError, match="尺寸/通道不一致"):
        watermark.embed(tmp_path / "a.png", tmp_path / "b.png", tmp_path / "o.png")


def test_embed_handles_chinese_path(tmp_path):
    rng = np.random.default_rng(7)
    cover = rng.integers(0, 256, (16, 16), dtype=np.uint8)
    folder = tmp_path / "中文 目录"
    folder.mkdir()
    Image.fromarray(cover).save(folder / "原图.png")
    Image.fromarray(cover).save(folder / "对比.png")
    out = watermark.embed(folder / "原图.png", folder / "对比.png", folder / "结果.png")
    assert out.exists()


def test_read_native_missing_file(tmp_path):
    with pytest.raises(StrikeError, match="文件不存在"):
        watermark.read_native(tmp_path / "nope.png")
