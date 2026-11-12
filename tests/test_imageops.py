# -*- coding: utf-8 -*-
"""像素运算类功能测试。"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from strike import imageops
from strike.errors import StrikeError


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "P", "L"])
def test_invert(tmp_path, make_png, mode):
    source = make_png(size=(40, 30), mode=mode)
    target = imageops.invert(source, tmp_path / "inv.png")

    original = np.asarray(Image.open(source).convert("RGBA"), dtype=np.uint8)
    inverted = np.asarray(Image.open(target).convert("RGBA"), dtype=np.uint8)
    np.testing.assert_array_equal(inverted[..., :3], 255 - original[..., :3])


def test_invert_missing_file(tmp_path):
    with pytest.raises(StrikeError, match="文件不存在"):
        imageops.invert(tmp_path / "nope.png", tmp_path / "out.png")


def test_rgb_to_image_square(tmp_path):
    txt = tmp_path / "rgb.txt"
    lines = ["0 0 0", "255 0 0", "0 255 0", "0 0 255"]
    txt.write_text("\n".join(lines), encoding="utf-8")

    out = tmp_path / "rgb.png"
    assert imageops.rgb_to_image(txt, out) == (2, 2)
    array = np.asarray(Image.open(out))
    assert tuple(array[0, 0]) == (0, 0, 0)
    assert tuple(array[0, 1]) == (255, 0, 0)
    assert tuple(array[1, 1]) == (0, 0, 255)


def test_rgb_to_image_tolerates_separators_and_crlf(tmp_path):
    txt = tmp_path / "rgb.txt"
    txt.write_bytes(b"10,20,30\r\n40\t50\t60\r\n70 80 90\r\n100 110 120\r\n")
    out = tmp_path / "rgb.png"
    assert imageops.rgb_to_image(txt, out) == (2, 2)


def test_rgb_to_image_rectangular(tmp_path):
    """行数不是完全平方数时按最接近正方形的因子对推断，并给出提示。"""
    txt = tmp_path / "rgb.txt"
    txt.write_text("\n".join(["1 2 3"] * 12), encoding="utf-8")
    lines: list[str] = []
    out = tmp_path / "rgb.png"
    width, height = imageops.rgb_to_image(txt, out, log=lines.append)
    assert width * height == 12
    assert any("不是完全平方数" in line for line in lines)


def test_rgb_to_image_bad_data(tmp_path):
    txt = tmp_path / "bad.txt"
    txt.write_text("hello world\n", encoding="utf-8")
    with pytest.raises(StrikeError, match="没有解析到任何 RGB"):
        imageops.rgb_to_image(txt, tmp_path / "o.png")


def test_binary_to_image(tmp_path):
    txt = tmp_path / "bits.txt"
    txt.write_text("1001", encoding="utf-8")  # 4 个 0/1 -> 2x2
    out = tmp_path / "bits.png"
    assert imageops.binary_to_image(txt, out) == (2, 2)
    array = np.asarray(Image.open(out))
    assert array.tolist() == [[0, 255], [255, 0]]  # 1 -> 黑


def test_binary_to_image_rectangular(tmp_path):
    txt = tmp_path / "bits2.txt"
    txt.write_text("1010\n0101\n", encoding="utf-8")  # 8 个 0/1 -> 2x4
    out = tmp_path / "bits2.png"
    assert imageops.binary_to_image(txt, out) == (2, 4)


def test_binary_to_image_ignores_other_chars(tmp_path):
    txt = tmp_path / "bits.txt"
    txt.write_text("1 0\n1 x0\n", encoding="utf-8")
    lines: list[str] = []
    out = tmp_path / "bits.png"
    assert imageops.binary_to_image(txt, out, log=lines.append) == (2, 2)
    assert any("忽略" in line for line in lines)


def test_binary_to_image_empty(tmp_path):
    txt = tmp_path / "empty.txt"
    txt.write_text("no bits here", encoding="utf-8")
    with pytest.raises(StrikeError, match="0/1"):
        imageops.binary_to_image(txt, tmp_path / "o.png")


def test_split_gif(tmp_path, make_gif, imgs_dir):
    gif = make_gif(frames=3)
    frames = imageops.split_gif(gif, imgs_dir / "gif")
    assert len(frames) == 3
    assert [path.name for path in frames] == ["frame1.png", "frame2.png", "frame3.png"]
    for path in frames:
        assert path.exists()


def test_split_gif_clears_stale_frames(tmp_path, make_gif, imgs_dir):
    target_dir = imgs_dir / "gif"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "frame9.png").write_bytes(b"stale")
    imageops.split_gif(make_gif(frames=2), target_dir)
    assert not (target_dir / "frame9.png").exists()


def test_split_gif_single_frame_raises(tmp_path):
    path = tmp_path / "single.gif"
    Image.new("RGB", (10, 10), "red").save(path)
    with pytest.raises(StrikeError, match="单帧"):
        imageops.split_gif(path, tmp_path / "out")
