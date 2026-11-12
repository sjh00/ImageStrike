# -*- coding: utf-8 -*-
"""ImageStrike 图形界面。

和命令行入口分开，好处是 GUI 可以被 offscreen 模式下的测试直接实例化，
而 `--cli` 模式完全不需要安装 PyQt5。
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import unquote

from PyQt5 import QtCore, QtGui, QtWidgets

from mainUi import Ui_ImageStrike
from strike import paths
from strike.jobs import MODES, run_job

BANNER = r"""
        ____                          _____ __       _ __
       /  _/___ ___  ____ _____ ____ / ___// /______(_) /_____
       / // __ `__ \/ __ `/ __ `/ _ \\__ \/ __/ ___/ / //_/ _ \
     _/ // / / / / / /_/ / /_/ /  __/__/ / /_/ /  / / ,< /  __/
    /___/_/ /_/ /_/\__,_/\__, /\___/____/\__/_/  /_/_/|_|\___/
                        /____/

                [+] Version: V0.3
                [+] Author : zR00t1（社区维护版）
                [+] Github : https://github.com/zR00t1/ImageStrike
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
"""

ENV_HINT = (
    "[*] 环境自检：F5 需要 java；pngcheck/steghide/foremost 来自 tools 目录。\n"
    "[*] 缺少某项依赖时只有对应功能不可用，其余功能不受影响。"
)

COLOR_OK = "#1a7f37"
COLOR_WARN = "#c62828"
COLOR_INFO = "#1f5fa8"
COLOR_LINE = "#9e9e9e"


def clean_path_text(text: str) -> str:
    """拖入/粘贴的路径常带 file:///、引号和换行，这里统一清理。"""
    if not text:
        return ""
    line = text.replace("\r", "\n").split("\n")[0].strip().strip('"').strip("'")
    lowered = line.lower()
    if lowered.startswith("file:///"):
        line = line[8:]
    elif lowered.startswith("file://"):
        line = line[7:]
    return unquote(line).strip()


class JobThread(QtCore.QThread):
    """把耗时的处理放到子线程，避免界面卡死。"""

    logline = QtCore.pyqtSignal(str)
    done = QtCore.pyqtSignal(object)

    def __init__(self, index: int, img1: str, img2: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.img1 = img1
        self.img2 = img2

    def run(self) -> None:  # noqa: D102 - QThread 接口
        try:
            result = run_job(self.index, self.img1, self.img2, log=self.logline.emit)
        except Exception as exc:  # noqa: BLE001 - 线程内异常必须回传界面
            self.logline.emit(f"[!] 未捕获的异常：{type(exc).__name__}: {exc}")
            result = None
        self.done.emit(result)


class MainEvents(QtWidgets.QMainWindow, Ui_ImageStrike):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.setFixedSize(self.width(), self.height())

        paths.ensure_imgs()
        self.thread: JobThread | None = None
        self.confirm_on_exit = True

        # 信号连接
        self.img1_text.textChanged.connect(self.change_text)
        self.img2_text.textChanged.connect(self.change_text)
        self.model_Box.currentIndexChanged.connect(self.my_combobox)
        self.pwnButton.clicked.connect(self.pwn)
        self.resetButton.clicked.connect(self.reset)

        # 预览区右键菜单
        self.imglabel.setStyleSheet("border: 2px solid #3a7bd5")
        self.imglabel.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.imglabel.customContextMenuRequested.connect(self.create_rightmenu)
        self.contextMenu = QtWidgets.QMenu(self)
        self.OP = self.contextMenu.addAction("打开图片")
        self.OPD = self.contextMenu.addAction("打开图片所在目录")
        self.QR = self.contextMenu.addAction("扫描二维码")
        self.IV = self.contextMenu.addAction("图片反相")
        self.CL = self.contextMenu.addAction("清空显示")
        self.OP.triggered.connect(self.showimg)
        self.OPD.triggered.connect(self.showdir)
        self.QR.triggered.connect(lambda: self.qrcode(self.infolabel.text()))
        self.IV.triggered.connect(lambda: self.inversion(self.infolabel.text()))
        self.CL.triggered.connect(self.resetimg)

        # 日志区右键菜单（复制/清空）
        self.info_text.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.info_text.customContextMenuRequested.connect(self.log_menu)

        # 双击路径框选择文件
        self.img1_text.viewport().installEventFilter(self)
        self.img2_text.viewport().installEventFilter(self)

        self.append_log(BANNER)
        self.append_log(ENV_HINT)
        self.my_combobox()

    # ---------------------------------------------------------- 日志与预览
    def append_log(self, line: str) -> None:
        color = None
        if line.startswith("[+]"):
            color = COLOR_OK
        elif line.startswith("[!]"):
            color = COLOR_WARN
        elif line.startswith("[*]"):
            color = COLOR_INFO
        elif line.startswith("- - -"):
            color = COLOR_LINE

        cursor = self.info_text.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        if color is None:
            cursor.insertText(line + "\n")
        else:
            fmt = QtGui.QTextCharFormat()
            fmt.setForeground(QtGui.QColor(color))
            cursor.insertText(line + "\n", fmt)
        self.info_text.setTextCursor(cursor)
        self.info_text.ensureCursorVisible()

    def show_preview(self, target) -> None:
        path = Path(target)
        if not path.exists():
            return
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            self.append_log(f"[!] 无法预览：{path.name}")
            return
        scaled = pixmap.scaled(
            self.imglabel.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.imglabel.setPixmap(scaled)
        self.infolabel.setText(str(path))

    def log_menu(self, pos) -> None:
        menu = QtWidgets.QMenu(self)
        copy_all = menu.addAction("复制全部输出")
        clear = menu.addAction("清空输出")
        action = menu.exec_(self.info_text.mapToGlobal(pos))
        if action is copy_all:
            QtWidgets.QApplication.clipboard().setText(self.info_text.toPlainText())
        elif action is clear:
            self.info_text.clear()

    # ---------------------------------------------------------- 输入处理
    def clean_path_text(self, text: str) -> str:
        return clean_path_text(text)

    def change_text(self) -> None:
        for widget in (self.img1_text, self.img2_text):
            original = widget.toPlainText()
            cleaned = self.clean_path_text(original)
            if cleaned != original:
                widget.blockSignals(True)
                widget.setText(cleaned)
                widget.blockSignals(False)

    def eventFilter(self, source, event):  # noqa: N802 - Qt 接口
        if event.type() == QtCore.QEvent.MouseButtonDblClick:
            if source is self.img1_text.viewport():
                self.pick_file(self.img1_text)
                return True
            if source is self.img2_text.viewport():
                self.pick_file(self.img2_text)
                return True
        return super().eventFilter(source, event)

    def pick_file(self, widget) -> None:
        current = widget.toPlainText().strip()
        start_dir = str(Path(current).parent) if current else str(paths.BASE_DIR)
        chosen, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择文件", start_dir, "所有文件 (*.*)"
        )
        if chosen:
            widget.setText(chosen)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 接口
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 接口
        files = [
            url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()
        ]
        if not files:
            return
        target = self.childAt(event.pos())
        widget = self.img2_text if target is self.img2_text else self.img1_text
        widget.setText(files[0])
        if len(files) > 1:
            self.img2_text.setText(files[1])
        event.acceptProposedAction()

    # ---------------------------------------------------------- 主流程
    def my_combobox(self) -> None:
        index = self.model_Box.currentIndex()
        self.append_log("- - - - - - - - - - - - - - - - - - - - - - - - - - - - -")
        if 0 <= index < len(MODES):
            mode = MODES[index]
            self.append_log(f"[*] 当前选择的隐写方式为：{mode.label}")
            self.append_log(f"[*] {mode.hint}")

    def is_busy(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def pwn(self) -> None:
        if self.is_busy():
            self.append_log("[!] 上一个任务还在运行，请稍候")
            return

        img1 = self.img1_text.toPlainText().strip()
        img2 = self.img2_text.toPlainText().strip()
        if not img1:
            self.append_log("[!] Img1 文件路径为空")
            return

        self.append_log("=" * 62)
        self._start(self.model_Box.currentIndex(), img1, img2)

    def _start(self, index: int, img1: str, img2: str) -> None:
        self.pwnButton.setEnabled(False)
        self.pwnButton.setText("运行中…")
        self.thread = JobThread(index, img1, img2, self)
        self.thread.logline.connect(self.append_log)
        self.thread.done.connect(self._job_finished)
        self.thread.start()

    def _job_finished(self, result) -> None:
        self.pwnButton.setEnabled(True)
        self.pwnButton.setText("Pwn")
        if result is not None and result.preview:
            self.show_preview(result.preview)

    def reset(self) -> None:
        self.img1_text.setPlainText("")
        self.img2_text.setPlainText("")

    # ---------------------------------------------------------- 预览区操作
    def qrcode(self, path_text: str) -> None:
        self._run_quick(3, path_text)

    def inversion(self, path_text: str) -> None:
        self._run_quick(4, path_text)

    def _run_quick(self, index: int, path_text: str) -> None:
        if not path_text:
            self.append_log("[!] 当前没有图片")
            return
        if self.is_busy():
            self.append_log("[!] 任务运行中，请稍候")
            return
        self._start(index, path_text, "")

    def create_rightmenu(self, pos) -> None:  # noqa: ARG002 - Qt 要求带参数
        self.contextMenu.exec_(QtGui.QCursor.pos())

    def showimg(self) -> None:
        path_text = self.infolabel.text()
        if path_text:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path_text))
        else:
            self.append_log("[!] 打开图片 - 当前没有图片")

    def showdir(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(paths.IMGS_DIR)))

    def resetimg(self) -> None:
        self.infolabel.setText("")
        self.imglabel.setPixmap(QtGui.QPixmap())

    # ---------------------------------------------------------- 关闭
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 接口
        if self.is_busy():
            self.append_log("[!] 任务仍在运行，请等待结束后再关闭")
            event.ignore()
            return
        if not self.confirm_on_exit:
            event.accept()
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "退出确认",
            "确定要退出 ImageStrike 吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()


def run_gui(argv: list[str] | None = None) -> int:
    # 高 DPI 支持必须在 QApplication 之前设置
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    app = QtWidgets.QApplication(list(argv if argv is not None else sys.argv))

    # 中文翻译包是可选的，缺失时不影响使用
    translator = QtCore.QTranslator()
    if translator.load(str(paths.BASE_DIR / "widgets_zh_CN.qm")):
        app.installTranslator(translator)

    window = MainEvents()
    window.show()
    return app.exec_()
