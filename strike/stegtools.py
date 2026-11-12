# -*- coding: utf-8 -*-
"""tools/ 下外部程序（pngcheck / F5 / steghide / foremost）的封装。

原始实现全部是 `subprocess.run('... {}'.format(path), shell=True)`：
路径带空格会被截断、带 & 会被拆成两条命令，且 GUI 下会闪黑框。
这里统一改成参数列表 + cwd 指定 + 超时保护。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import paths
from .errors import StrikeError, ToolMissingError
from .proc import output_text, run, which


def _require(path: Path, hint: str) -> Path:
    if not path.exists():
        raise ToolMissingError(f"缺少外部程序 {path.name}（应在 {path.parent}），{hint}")
    return path


def pngcheck(path: Path | str, *, log=None) -> str:
    """PNG 结构检查，输出 pngcheck -v 的原始文本。"""
    exe = _require(paths.tool("pngcheck", "pngcheck.exe"), "请重新克隆仓库以恢复 tools 目录")
    path = Path(path)
    if not path.exists():
        raise StrikeError(f"文件不存在：{path}")
    result = run([str(exe), "-v", str(path)], timeout=60)
    text = output_text(result).strip()
    if log:
        log(f"[*] pngcheck 退出码：{result.returncode}")
    return text or "（pngcheck 没有输出）"


def _java() -> str:
    java = which("java")
    if not java:
        raise ToolMissingError("未检测到 java.exe，F5 隐写需要先安装 JDK/JRE 并加入 PATH")
    return java


def f5_extract(path: Path | str, password: str | None = None, *, log=None) -> tuple[str, str]:
    """F5 提取，返回 (状态, 文本)。状态：ok / not_f5 / error。"""
    f5_dir = paths.tool("F5")
    _require(f5_dir / "Extract.class", "请重新克隆仓库以恢复 tools/F5 目录")
    path = Path(path).resolve()
    if not path.exists():
        raise StrikeError(f"文件不存在：{path}")

    java = _java()
    # 输出到 imgs/ 下，避免覆盖仓库自带的 tools/F5/output.txt
    out_file = paths.out_path("f5_out.txt")
    if out_file.exists():
        out_file.unlink()

    passphrase = password or "abc123"  # F5 工具的默认口令
    argv = [
        java,
        "-cp",
        str(f5_dir),
        "Extract",
        str(path),
        "-p",
        passphrase,
        "-e",
        str(out_file),
    ]
    result = run(argv, cwd=f5_dir, timeout=120)
    raw = output_text(result).strip()

    produced = out_file.exists() and out_file.stat().st_size > 0
    if produced and result.returncode == 0:
        text = out_file.read_text(encoding="utf-8", errors="replace")
        if log:
            log(f"[*] 提取结果已写入 {out_file}")
        return "ok", text

    # 失败时 F5 会留下一个 0 字节文件，清掉免得下次误判
    if out_file.exists():
        out_file.unlink()

    if result.returncode != 0 or "Incomplete file" in raw or "EOFException" in raw:
        return "not_f5", raw
    return "error", raw


def steghide_extract(
    path: Path | str, password: str | None = None, *, log=None
) -> tuple[bool, str, list[Path]]:
    """steghide 提取。密码留空时会先试空口令，再给出提示。"""
    exe = _require(
        paths.tool("steghide", "steghide.exe"), "请重新克隆仓库以恢复 tools/steghide 目录"
    )
    path = Path(path).resolve()
    if not path.exists():
        raise StrikeError(f"文件不存在：{path}")

    work_dir = paths.out_dir("steghide_out")
    for stale in work_dir.iterdir():
        if stale.is_file():
            stale.unlink()
        else:
            shutil.rmtree(stale, ignore_errors=True)

    passphrases = [password] if password else ["", "abc123"]
    messages: list[str] = []

    for candidate in passphrases:
        label = "空口令" if candidate == "" else f"口令 {candidate}"
        argv = [
            str(exe),
            "extract",
            "-sf",
            str(path),
            "-p",
            candidate or "",
            "-f",
        ]
        result = run(argv, cwd=work_dir, timeout=120)
        text = (output_text(result) or "").strip()
        produced = [item for item in work_dir.iterdir() if item.is_file()]
        if produced:
            if log:
                log(f"[+] 使用{label}提取成功")
            return True, text, produced
        messages.append(f"--- 尝试{label} ---\n{text or '（无输出）'}")

    return False, "\n".join(messages), []


def foremost(path: Path | str, *, log=None) -> tuple[bool, str, Path]:
    """foremost 文件雕刻，输出到 imgs/foremost_out。

    原脚本用的是 `foremost.exe <file> -T`，这里有三处必须修：
    1. 没有配置文件：foremost 默认去 "C:\\Program Files\\foremost\\foremost.conf"
       找配置，找不到就直接退出，所以这个功能从来没真正跑通过 -> 用 -c 指定自带配置；
    2. `-T`（加时间戳日志）会让这个 Windows 构建一个文件都不恢复 -> 去掉；
    3. `-q` 只在 512 字节边界搜索，会漏掉非对齐的嵌入文件 -> 不用。
    """
    exe = _require(
        paths.tool("foremost", "foremost.exe"), "请重新克隆仓库以恢复 tools/foremost 目录"
    )
    conf = _require(
        paths.tool("foremost", "foremost.conf"), "请重新克隆仓库以恢复 tools/foremost 目录"
    )
    path = Path(path).resolve()
    if not path.exists():
        raise StrikeError(f"文件不存在：{path}")

    out_dir = paths.out_dir("foremost_out")
    result = run(
        [
            str(exe),
            "-c",
            str(conf),
            "-i",
            str(path),
            "-o",
            str(out_dir),
            "-Q",
        ],
        timeout=600,
    )
    text = (output_text(result) or "").strip()

    produced: list[Path] = []
    for item in sorted(out_dir.rglob("*")):
        if item.is_file() and item.name not in ("audit.txt", "progress.log"):
            produced.append(item)

    if log:
        if produced:
            counts: dict[str, int] = {}
            for item in produced:
                counts[item.suffix or "无后缀"] = counts.get(item.suffix or "无后缀", 0) + 1
            summary = "，".join(f"{k} {v} 个" for k, v in sorted(counts.items()))
            log(f"[*] foremost 恢复出 {len(produced)} 个文件：{summary}")
        else:
            log("[!] foremost 没有恢复出文件")

    return bool(produced), text, out_dir
