# -*- coding: utf-8 -*-
"""元数据读取测试。

pyexiv2 是可选依赖，所以用例同时兼容两条路径：
装了 pyexiv2 时键名是 `Exif.Image.ImageDescription` 风格，
没装时用 Pillow 兜底，键名是 `ImageDescription` 风格。
"""

from __future__ import annotations

import pytest
from PIL import Image

from strike import metadata
from strike.errors import StrikeError

XMP_PACKET = (
    b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>'
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
    b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    b'<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">'
    b"<dc:format>image/jpeg</dc:format>"
    b"</rdf:Description></rdf:RDF></x:xmpmeta>"
    b'<?xpacket end="w"?>'
)


@pytest.fixture()
def jpeg_with_exif(tmp_path):
    path = tmp_path / "exif.jpg"
    image = Image.new("RGB", (64, 48), "red")
    exif = image.getexif()
    exif[0x010E] = "ImageStrike 描述"
    exif[0x0131] = "ImageStrike"
    image.save(path, exif=exif)
    return path


def test_basic_info(make_png):
    info = metadata.basic_info(make_png(size=(40, 30)))
    assert info["图片格式"] == "PNG"
    assert info["图片尺寸"] == "40x30"
    assert info["色彩模式"] in {"RGB", "P", "L", "RGBA"}
    assert "文件大小" in info


def test_basic_info_unknown_format(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    info = metadata.basic_info(bad)
    assert "无法识别" in info["图片格式"]


def test_basic_info_missing_file(tmp_path):
    with pytest.raises(StrikeError, match="文件不存在"):
        metadata.basic_info(tmp_path / "nope.png")


def test_exif_is_read(jpeg_with_exif):
    sections = metadata.read_metadata(jpeg_with_exif)
    assert "EXIF" in sections
    keys = " ".join(sections["EXIF"])
    assert "ImageDescription" in keys


def test_xmp_is_read(tmp_path, jpeg_with_exif):
    target = tmp_path / "with_xmp.jpg"
    with Image.open(jpeg_with_exif) as img:
        try:
            img.save(target, xmp=XMP_PACKET)
        except (TypeError, ValueError):
            pytest.skip("当前 Pillow 不支持写入 XMP")
    sections = metadata.read_metadata(target)
    assert "XMP" in sections


def test_image_without_metadata(make_png):
    """没有元数据时不应该抛异常，只返回基本信息。"""
    sections = metadata.read_metadata(make_png())
    assert "基本信息" in sections
    assert "EXIF" not in sections or sections["EXIF"]


def test_gif_frames_counted(make_gif):
    info = metadata.basic_info(make_gif(frames=3))
    assert info["图片格式"] == "GIF"
    assert info["帧数"] == "3"
