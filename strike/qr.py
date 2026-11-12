# -*- coding: utf-8 -*-
"""二维码/条码识别。

主引擎换成仍在维护的 zxing-cpp（识别率明显好于已停更的 pyzbar），
pyzbar 作为可选兜底；两者都不可用或都失败时，再对图片做预处理重试。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from .errors import StrikeError


def _load(path: Path | str) -> Image.Image:
    path = Path(path)
    if not path.exists():
        raise StrikeError(f"文件不存在：{path}")
    try:
        img = Image.open(path)
        img.load()
    except OSError as exc:
        raise StrikeError(f"无法识别的图片格式：{path.name}（{exc}）") from exc
    return img


def _variants(img: Image.Image):
    """依次产出（说明, 图片）用于重试。"""
    base = img.convert("L")
    yield "原图", base
    yield "增强对比度", ImageOps.autocontrast(base)
    yield "反相", ImageOps.invert(base)
    for scale in (2, 3):
        yield f"放大{scale}倍", base.resize(
            (base.width * scale, base.height * scale), Image.LANCZOS
        )


def _zxing(img: Image.Image) -> list[tuple[str, str]]:
    try:
        import zxingcpp
    except ImportError:
        return []
    try:
        results = zxingcpp.read_barcodes(img)
    except Exception:  # noqa: BLE001 - 原生库异常不应打断整个流程
        return []
    return [(str(getattr(r, "format", "BARCODE")), r.text) for r in results if r.text]


def _pyzbar(img: Image.Image) -> list[tuple[str, str]]:
    try:
        from pyzbar import pyzbar
    except Exception:  # noqa: BLE001 - 缺少 libzbar 时连导入都会失败
        return []
    try:
        results = pyzbar.decode(img)
    except Exception:  # noqa: BLE001
        return []
    hits = []
    for item in results:
        text = item.data.decode("utf-8", "replace")
        if text:
            hits.append((item.type, text))
    return hits


def decode_qr(path: Path | str, *, log=None) -> list[tuple[str, str]]:
    """返回 [(类型, 内容)]，去重后保持顺序。"""
    img = _load(path)
    engines = []
    try:
        import zxingcpp  # noqa: F401

        engines.append(("zxing-cpp", _zxing))
    except ImportError:
        pass
    if _has_pyzbar():
        engines.append(("pyzbar", _pyzbar))

    if not engines:
        raise StrikeError(
            "没有可用的二维码识别引擎，请安装 zxing-cpp（uv sync 已包含）或 pyzbar"
        )

    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for label, variant in _variants(img):
        for engine_name, engine in engines:
            for kind, text in engine(variant):
                key = (kind, text)
                if key in seen:
                    continue
                seen.add(key)
                found.append(key)
                if log:
                    log(f"[+] {engine_name} 在「{label}」上识别到 {kind}")
        if found:
            break
    img.close()
    return found


def _has_pyzbar() -> bool:
    try:
        import pyzbar  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True
