# -*- coding: utf-8 -*-
"""图片元数据（EXIF / IPTC / XMP）读取。

优先用 pyexiv2（可选依赖），未安装或解析失败时回退到 Pillow + 原始字节扫描，
保证“没装 pyexiv2 也能看 EXIF/XMP”，而不是直接抛异常。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ExifTags

from .errors import StrikeError

_XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"
_MAX_VALUE_LEN = 300


def _short(value) -> str:
    text = str(value)
    if len(text) > _MAX_VALUE_LEN:
        text = text[:_MAX_VALUE_LEN] + f"…（共 {len(text)} 字符）"
    return text


def basic_info(path: Path | str) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        raise StrikeError(f"文件不存在：{path}")
    info: dict[str, str] = {
        "文件名": path.name,
        "文件大小": f"{path.stat().st_size} 字节",
    }
    try:
        with Image.open(path) as img:
            info["图片格式"] = img.format or "未知"
            info["色彩模式"] = img.mode
            info["图片尺寸"] = f"{img.size[0]}x{img.size[1]}"
            frames = getattr(img, "n_frames", 1)
            if frames > 1:
                info["帧数"] = str(frames)
    except OSError as exc:
        info["图片格式"] = f"无法识别（{exc}）"
    return info


def _exif_from_pillow(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with Image.open(path) as img:
        exif = img.getexif()
        if not exif:
            return result
        for tag_id, value in exif.items():
            name = ExifTags.TAGS.get(tag_id, f"Tag{tag_id}")
            result[name] = _short(value)
        # 子 IFD 里才是最常用的拍摄参数
        for ifd_name, ifd_id in (("Exif", 0x8769), ("GPS", 0x8825)):
            try:
                sub = exif.get_ifd(ifd_id)
            except Exception:  # noqa: BLE001 - 不同 Pillow 版本行为不一致
                continue
            for tag_id, value in (sub or {}).items():
                name = ExifTags.TAGS.get(tag_id, f"Tag{tag_id}")
                result[f"{ifd_name}.{name}"] = _short(value)
    return result


def _xmp_from_raw(path: Path) -> str:
    """从原始字节里捞出 XMP 包（Pillow 不解码 XMP）。"""
    raw = path.read_bytes()
    start = raw.find(_XMP_HEADER)
    if start < 0:
        start = raw.find(b"<x:xmpmeta")
        if start < 0:
            return ""
        end = raw.find(b"</x:xmpmeta>", start)
    else:
        start += len(_XMP_HEADER)
        end = raw.find(b"<?xpacket end=", start)
        if end < 0:
            end = raw.find(b"</x:xmpmeta>", start)
    if end < 0:
        return ""
    payload = raw[start:end]
    return payload.decode("utf-8", "replace").strip()


def read_metadata(path: Path | str, *, log=None) -> dict[str, dict[str, str]]:
    """返回 {分组标题: {键: 值}}。"""
    path = Path(path)
    sections: dict[str, dict[str, str]] = {"基本信息": basic_info(path)}

    exif: dict[str, str] = {}
    iptc: dict[str, str] = {}
    xmp: dict[str, str] = {}
    notes: list[str] = []

    try:
        import pyexiv2  # 可选依赖
    except ImportError:
        pyexiv2 = None
        notes.append("未安装可选依赖 pyexiv2，EXIF 用 Pillow 兜底解析，IPTC 不可用")

    if pyexiv2 is not None:
        try:
            handle = pyexiv2.Image(str(path), encoding="utf-8")
            try:
                exif = {k: _short(v) for k, v in handle.read_exif().items()}
                iptc = {k: _short(v) for k, v in handle.read_iptc().items()}
                xmp = {k: _short(v) for k, v in handle.read_xmp().items()}
            finally:
                handle.close()
        except Exception as exc:  # noqa: BLE001 - pyexiv2 对格式很敏感
            notes.append(f"pyexiv2 解析失败（{type(exc).__name__}: {exc}），已回退到 Pillow")
            exif, iptc, xmp = {}, {}, {}

    if not exif:
        try:
            exif = _exif_from_pillow(path)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Pillow 读取 EXIF 失败：{type(exc).__name__}: {exc}")

    if not xmp:
        try:
            raw_xmp = _xmp_from_raw(path)
        except OSError:
            raw_xmp = ""
        if raw_xmp:
            xmp = {"原始XMP": _short(raw_xmp)}

    if exif:
        sections["EXIF"] = exif
    if iptc:
        sections["IPTC"] = iptc
    if xmp:
        sections["XMP"] = xmp
    if notes:
        sections["提示"] = {str(i + 1): note for i, note in enumerate(notes)}

    if log:
        log(f"[*] 元数据读取完成：EXIF {len(exif)} 项，IPTC {len(iptc)} 项，XMP {len(xmp)} 项")
    return sections
