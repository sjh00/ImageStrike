# -*- coding: utf-8 -*-
"""测试夹具：生成各种待处理文件，并把输出目录重定向到临时目录。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strike import paths  # noqa: E402


@pytest.fixture()
def imgs_dir(tmp_path, monkeypatch):
    """把 strike.paths.IMGS_DIR 指向临时目录，避免污染仓库里的 imgs/。"""
    target = tmp_path / "imgs"
    monkeypatch.setattr(paths, "IMGS_DIR", target)
    target.mkdir(parents=True, exist_ok=True)
    return target


@pytest.fixture()
def make_png(tmp_path):
    def _make(name: str = "pic.png", size=(320, 200), mode: str = "RGB") -> Path:
        width, height = size
        array = np.zeros((height, width, 3), dtype=np.uint8)
        array[:, :, 0] = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
        array[:, :, 1] = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
        array[:, :, 2] = 128
        image = Image.fromarray(array)
        if mode == "RGBA":
            image = image.convert("RGBA")
            alpha = np.linspace(0, 255, width * height, dtype=np.uint8)
            image.putalpha(Image.fromarray(alpha.reshape(height, width)))
        elif mode == "P":
            image = image.convert("P")
        elif mode == "L":
            image = image.convert("L")
        target = tmp_path / name
        image.save(target)
        return target

    return _make


@pytest.fixture()
def make_jpeg(tmp_path):
    def _make(name: str = "pic.jpg", size=(320, 200)) -> Path:
        width, height = size
        array = np.zeros((height, width, 3), dtype=np.uint8)
        array[:, :, 0] = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
        array[:, :, 1] = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
        array[:, :, 2] = 60
        target = tmp_path / name
        Image.fromarray(array).save(target, "JPEG", quality=95)
        return target

    return _make


@pytest.fixture()
def make_gif(tmp_path):
    def _make(name: str = "anim.gif", frames: int = 3, size=(60, 40)) -> Path:
        images = []
        for index in range(frames):
            array = np.full((size[1], size[0], 3), index * 60, dtype=np.uint8)
            array[:, :, 0] = np.linspace(0, 255, size[0], dtype=np.uint8)[None, :]
            images.append(Image.fromarray(array))
        target = tmp_path / name
        images[0].save(
            target, save_all=True, append_images=images[1:], duration=100, loop=0
        )
        return target

    return _make


_QR_SCRIPT = r"""
import sys
import numpy as np
import zxingcpp
from PIL import Image

text, out = sys.argv[1], sys.argv[2]
barcode = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.QRCode)
array = np.array(zxingcpp.write_barcode_to_image(barcode), dtype=np.uint8)
image = Image.fromarray(array)
if image.mode != "L":
    image = image.convert("L")
scale = max(4, 240 // max(image.width, 1))
image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
image.convert("RGB").save(out)
"""


@pytest.fixture()
def make_qr(tmp_path):
    """生成一张二维码图片。

    注意：zxing-cpp 的 create_barcode 在同一个进程里跟 Qt 初始化过之后会崩
    （access violation），而 read_barcodes 不受影响。所以这里用子进程生成，
    避免 GUI 测试先跑时把后面的用例带崩。
    """

    def _make(text: str = "flag{ImageStrike}", name: str = "qr.png"):
        import subprocess
        import sys

        target = tmp_path / name
        subprocess.run(
            [sys.executable, "-c", _QR_SCRIPT, text, str(target)],
            check=True,
            capture_output=True,
        )
        return target

    return _make
