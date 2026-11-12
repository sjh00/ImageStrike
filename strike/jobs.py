# -*- coding: utf-8 -*-
"""隐写方式定义与任务调度。

界面下拉框、提示语、实际处理逻辑都以 `MODES` 为唯一来源，
避免“界面加了选项、代码忘了分支”这类问题（原版 All in One 就是空的）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import dimfix, imageops, metadata, qr, stegpy_extract, stegtools, watermark
from .errors import StrikeError, ToolMissingError
from .paths import out_dir, out_path
from .textscan import extract_strings


@dataclass(frozen=True)
class Mode:
    index: int
    label: str
    hint: str
    needs: str  # img1 / both / txt / none


MODES: tuple[Mode, ...] = (
    Mode(0, "All in One（一键自动分析）", "Img1 填入待分析文件，自动做一遍常见检测", "img1"),
    Mode(1, "[01] 盲水印（旧版种子 / oldseed）", "Img1 填原图，Img2 填加密图，两张尺寸必须一致", "both"),
    Mode(2, "[02] 盲水印（新版种子）", "Img1 填原图，Img2 填加密图，两张尺寸必须一致", "both"),
    Mode(3, "[03] 二维码扫描", "Img1 填入图片路径", "img1"),
    Mode(4, "[04] 图片反相", "Img1 填入图片路径", "img1"),
    Mode(5, "[05] RGB -> 图片", "Img1 填入 txt 路径，每行三组 RGB 值，例：255 255 255", "txt"),
    Mode(6, "[06] PNG改宽高", "Img1 填入 png 路径，按 IHDR 的 CRC 暴力还原宽高", "img1"),
    Mode(7, "[07] PNG IDAT检测", "Img1 填入 png 路径", "img1"),
    Mode(8, "[08] 图片元数据（EXIF、IPTC、XMP）", "Img1 填入图片路径", "img1"),
    Mode(9, "[09] Gif帧分离", "Img1 填入 gif 路径", "img1"),
    Mode(10, "[10] F5隐写（需java环境）", "Img1 填文件路径，Img2 填密码（留空用默认 abc123）", "img1"),
    Mode(11, "[11] Strings可打印字符", "Img1 填文件路径，输出带十六进制偏移", "img1"),
    Mode(12, "[12] JPG改高度（原始高度*2）", "Img1 填入 jpg 路径", "img1"),
    Mode(13, "[13] JPG改宽度（原始宽度*2）", "Img1 填入 jpg 路径", "img1"),
    Mode(14, "[14] 二进制 -> 黑白矩阵", "Img1 填入 txt 路径，内容为 0/1", "txt"),
    Mode(15, "[15] Stegpy", "Img1 填文件路径，Img2 填密码（无密码留空）", "img1"),
    Mode(16, "[16] Steghide", "Img1 填文件路径，Img2 填密码（留空会先试空口令）", "img1"),
    Mode(17, "[17] Foremost", "Img1 填文件路径，结果输出到 imgs/foremost_out", "img1"),
)


@dataclass
class JobResult:
    ok: bool
    preview: Path | None = None
    extra: dict = field(default_factory=dict)


def _mode(index: int) -> Mode:
    for mode in MODES:
        if mode.index == index:
            return mode
    raise StrikeError(f"未知的隐写方式编号：{index}")


def _check_img1(img1: str) -> Path:
    text = (img1 or "").strip().strip('"')
    if not text:
        raise StrikeError("Img1 文件路径为空")
    path = Path(text)
    if not path.exists():
        raise StrikeError(f"Img1 路径不存在：{path}")
    if path.is_dir():
        raise StrikeError(f"Img1 是目录而不是文件：{path}")
    return path


def _check_img2(img2: str) -> Path:
    text = (img2 or "").strip().strip('"')
    if not text:
        raise StrikeError("Img2 文件路径为空")
    path = Path(text)
    if not path.exists():
        raise StrikeError(f"Img2 路径不存在：{path}")
    return path


def _pw(img2: str) -> str | None:
    """Img2 在需要密码的模式里当密码用。"""
    text = (img2 or "").strip()
    return text or None


# ---------------------------------------------------------------- 各功能实现


def _do_watermark(img1: str, img2: str, oldseed: bool, log) -> JobResult:
    cover = _check_img1(img1)
    marked = _check_img2(img2)
    name = "result1.png" if oldseed else "result2.png"
    target = out_path(name)
    log(f"[*] 盲水印：{'旧版种子(oldseed)' if oldseed else '新版种子'}")
    watermark.embed(cover, marked, target, oldseed=oldseed, log=log)
    return JobResult(True, target)


def _do_qrcode(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    hits = qr.decode_qr(path, log=log)
    if not hits:
        log("[!] 未识别到二维码/条码")
        return JobResult(False)
    for kind, text in hits:
        log(f"[+] {kind}：{text}")
    return JobResult(True)


def _do_invert(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    target = imageops.invert(path, out_path("result4.png"))
    log(f"[+] 反相完成：{target}")
    return JobResult(True, target)


def _do_rgb2img(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    target = out_path("result5.png")
    imageops.rgb_to_image(path, target, log=log)
    return JobResult(True, target)


def _do_png_fix(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    target = out_path("result6.png")
    width, height = dimfix.fix_png_size(path, target, log=log)
    return JobResult(True, target, {"size": (width, height)})


def _do_png_check(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    text = stegtools.pngcheck(path, log=log)
    for line in text.splitlines():
        log(line)
    return JobResult(True)


def _do_metadata(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    sections = metadata.read_metadata(path, log=log)
    for title, values in sections.items():
        log(f"[*] {title}：")
        if not values:
            log("    （无）")
            continue
        for key, value in values.items():
            log(f"    {key}: {value}")
    return JobResult(bool(sections))


def _do_gif(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    frames = imageops.split_gif(path, out_dir("gif"), log=log)
    return JobResult(True, frames[0] if frames else None)


def _do_f5(img1: str, img2: str, log) -> JobResult:
    path = _check_img1(img1)
    status, text = stegtools.f5_extract(path, _pw(img2), log=log)
    if status == "ok":
        log("[+] F5 提取成功：")
        for line in text.splitlines():
            log(line)
        return JobResult(True)
    if status == "not_f5":
        log("[!] 该图片可能不是 F5 隐写，或密码错误")
    else:
        log("[!] F5 执行失败，输出如下：")
        for line in (text or "（无输出）").splitlines():
            log(line)
    return JobResult(False)


def _do_strings(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    hits, total = extract_strings(path)
    for offset, text in hits:
        log(f"0x{offset:08x}  {text}")
    log(f"[*] 共命中 {total} 条可打印字符串，已展示 {len(hits)} 条")
    return JobResult(bool(hits))


def _do_jpg_fix(img1: str, axis: str, log) -> JobResult:
    path = _check_img1(img1)
    name = "result12.jpg" if axis == "h" else "result13.jpg"
    target = out_path(name)
    dimfix.fix_jpeg_size(path, target, axis=axis, log=log)
    return JobResult(True, target)


def _do_bin2img(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    target = out_path("result14.png")
    imageops.binary_to_image(path, target, log=log)
    return JobResult(True, target)


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".jfif", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def _as_preview(path: Path | None) -> Path | None:
    """只有图片才丢给界面预览，文本/二进制文件不预览。"""
    if path is None or not path.exists():
        return None
    return path if path.suffix.lower() in _IMAGE_SUFFIXES else None


def _do_stegpy(img1: str, img2: str, log) -> JobResult:
    path = _check_img1(img1)
    text, produced = stegpy_extract.extract(path, _pw(img2), log=log)
    log(f"[+] {text}")
    return JobResult(True, _as_preview(produced))


def _do_steghide(img1: str, img2: str, log) -> JobResult:
    path = _check_img1(img1)
    ok, text, produced = stegtools.steghide_extract(path, _pw(img2), log=log)
    if text:
        for line in text.splitlines():
            log(line)
    if ok:
        for item in produced:
            log(f"[+] 已提取：{item}")
        return JobResult(True, _as_preview(produced[0]) if produced else None)
    log("[!] steghide 未能提取出内容：口令为空、口令错误，或该文件不含 steghide 隐写")
    return JobResult(False)


def _do_foremost(img1: str, log) -> JobResult:
    path = _check_img1(img1)
    ok, text, out_dir_path = stegtools.foremost(path, log=log)
    if text:
        for line in text.splitlines():
            log(line)
    return JobResult(ok, None, {"out_dir": out_dir_path})


def _do_all_in_one(img1: str, log) -> JobResult:
    """一键巡检：只做快速、只读的检测，不做 foremost 这类耗时操作。"""
    path = _check_img1(img1)
    suffix = path.suffix.lower()
    results: dict[str, bool] = {}

    def section(title: str) -> None:
        log("- - - - - - - - - - - - - - - - - - - - - - - - - - - - -")
        log(f"[*] {title}")

    def attempt(name: str, func, *args) -> None:
        try:
            outcome = func(*args)
            # 子检测返回 JobResult 时以它的结论为准，避免“跑完就当成有结果”
            results[name] = bool(getattr(outcome, "ok", True))
        except (StrikeError, ToolMissingError) as exc:
            log(f"[!] {name} 跳过：{exc}")
            results[name] = False
        except Exception as exc:  # noqa: BLE001 - 单项失败不影响后续巡检
            log(f"[!] {name} 异常：{type(exc).__name__}: {exc}")
            results[name] = False

    section("基本信息与元数据")
    attempt("元数据", _do_metadata, str(path), log)

    section("二维码/条码")
    attempt("二维码", _do_qrcode, str(path), log)

    section("可打印字符串（前 40 条）")
    try:
        hits, total = extract_strings(path, limit=40)
        for offset, text in hits:
            log(f"0x{offset:08x}  {text}")
        log(f"[*] 共命中 {total} 条，已展示 {len(hits)} 条，完整列表请用 [11] Strings 模式")
        results["字符串"] = bool(hits)
    except StrikeError as exc:
        log(f"[!] 字符串提取失败：{exc}")
        results["字符串"] = False

    if suffix == ".png":
        section("PNG 结构检查")
        attempt("pngcheck", _do_png_check, str(path), log)
        try:
            width, height = dimfix.png_size(path)
            log(f"[*] IHDR 声明尺寸：{width}x{height}")
        except StrikeError as exc:
            log(f"[!] IHDR 读取失败：{exc}")
    elif suffix in (".jpg", ".jpeg", ".jfif"):
        section("JPEG 结构检查")
        try:
            width, height = dimfix.jpeg_size(path)
            log(f"[*] SOF 声明尺寸：{width}x{height}")
            results["JPEG 尺寸"] = True
        except StrikeError as exc:
            log(f"[!] SOF 读取失败：{exc}")
        attempt("steghide", _do_steghide, str(path), "", log)
    elif suffix == ".gif":
        section("GIF 拆帧")
        attempt("GIF 拆帧", _do_gif, str(path), log)

    section("stegpy(stegv3) 探测")
    attempt("stegpy", _do_stegpy, str(path), "", log)

    section("巡检结论")
    ok_items = [name for name, ok in results.items() if ok]
    if ok_items:
        log(f"[+] 有结果的检测项：{'、'.join(ok_items)}")
    else:
        log("[!] 未发现明显线索，可再尝试 F5 / 盲水印 / Foremost")
    preview = out_path("gif/frame1.png") if suffix == ".gif" else None
    return JobResult(bool(ok_items), preview, {"results": results})


# ------------------------------------------------------------------ 统一入口

_DISPATCH = {
    0: lambda img1, img2, log: _do_all_in_one(img1, log),
    1: lambda img1, img2, log: _do_watermark(img1, img2, True, log),
    2: lambda img1, img2, log: _do_watermark(img1, img2, False, log),
    3: lambda img1, img2, log: _do_qrcode(img1, log),
    4: lambda img1, img2, log: _do_invert(img1, log),
    5: lambda img1, img2, log: _do_rgb2img(img1, log),
    6: lambda img1, img2, log: _do_png_fix(img1, log),
    7: lambda img1, img2, log: _do_png_check(img1, log),
    8: lambda img1, img2, log: _do_metadata(img1, log),
    9: lambda img1, img2, log: _do_gif(img1, log),
    10: lambda img1, img2, log: _do_f5(img1, img2, log),
    11: lambda img1, img2, log: _do_strings(img1, log),
    12: lambda img1, img2, log: _do_jpg_fix(img1, "h", log),
    13: lambda img1, img2, log: _do_jpg_fix(img1, "w", log),
    14: lambda img1, img2, log: _do_bin2img(img1, log),
    15: lambda img1, img2, log: _do_stegpy(img1, img2, log),
    16: lambda img1, img2, log: _do_steghide(img1, img2, log),
    17: lambda img1, img2, log: _do_foremost(img1, log),
}

SEPARATOR = "- - - - - - - - - - - - - - - - - - - - - - - - - - - - -"


def run_job(index: int, img1: str = "", img2: str = "", *, log=None) -> JobResult:
    """执行指定隐写方式。log 可传入任何接收字符串的可调用对象。"""
    mode = _mode(index)
    emit = log or (lambda _msg: None)

    emit(f"[*] 当前选择的隐写方式为：{mode.label}")
    emit(f"[*] {mode.hint}")

    handler = _DISPATCH.get(index)
    try:
        if handler is None:
            raise StrikeError(f"该方式尚未实现：{mode.label}")
        result = handler(img1, img2, emit)
    except (StrikeError, ToolMissingError) as exc:
        emit(f"[!] {exc}")
        result = JobResult(False)
    except Exception as exc:  # noqa: BLE001 - 兜底，保证界面不会因单项异常而中断
        emit(f"[!] 未捕获的异常：{type(exc).__name__}: {exc}")
        result = JobResult(False)

    emit("[+] 执行成功" if result.ok else "[!] 执行结束，未得到有效结果")
    emit(SEPARATOR)
    return result
