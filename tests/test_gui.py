# -*- coding: utf-8 -*-
"""界面层测试（offscreen 模式，不需要真实显示器）。

覆盖的是“界面和逻辑之间的接线”：下拉框与 MODES 同步、路径清洗、
未填路径时的提示、后台线程跑完能回到界面。
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5 import QtWidgets  # noqa: E402

from strike.jobs import MODES  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture()
def window(qapp, imgs_dir):
    from gui import MainEvents

    win = MainEvents()
    win.confirm_on_exit = False  # 避免关闭时弹出模态确认框卡住测试
    yield win
    if win.thread is not None and win.thread.isRunning():
        win.thread.wait(10000)
    win.close()


def wait_idle(window, timeout: float = 20.0) -> None:
    """跑事件循环直到后台线程结束。"""
    deadline = time.time() + timeout
    while window.is_busy() and time.time() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.02)
    QtWidgets.QApplication.processEvents()
    assert not window.is_busy(), "后台任务超时未结束"


def test_combobox_matches_modes(window):
    assert window.model_Box.count() == len(MODES)
    for index, mode in enumerate(MODES):
        assert window.model_Box.itemText(index) == mode.label


def test_initial_log_contains_banner(window):
    text = window.info_text.toPlainText()
    assert "ImageStrike" in text
    assert "当前选择的隐写方式" in text


def test_switching_mode_logs_hint(window):
    window.model_Box.setCurrentIndex(6)
    assert MODES[6].hint in window.info_text.toPlainText()


def test_pwn_without_img1_logs_warning(window):
    window.img1_text.setPlainText("")
    window.pwn()
    assert "Img1 文件路径为空" in window.info_text.toPlainText()
    assert window.thread is None


def test_clean_path_text():
    from gui import clean_path_text

    cases = {
        "file:///C:/a/b.png": "C:/a/b.png",
        '  "C:\\a b\\pic.png"  ': "C:\\a b\\pic.png",
        "C:/a%20b/pic.png": "C:/a b/pic.png",
        "C:/a/pic.png\nC:/b/pic.png": "C:/a/pic.png",
        "": "",
    }
    for raw, expected in cases.items():
        assert clean_path_text(raw) == expected


def test_change_text_strips_file_url(window):
    window.img1_text.setPlainText("file:///C:/tmp/x.png")
    assert window.img1_text.toPlainText() == "C:/tmp/x.png"


def test_job_runs_in_background_and_previews(window, make_png):
    window.model_Box.setCurrentIndex(4)  # 图片反相
    window.img1_text.setPlainText(str(make_png()))
    window.pwn()

    assert window.pwnButton.isEnabled() is False
    wait_idle(window)
    assert window.pwnButton.isEnabled() is True
    assert window.pwnButton.text() == "Pwn"
    assert window.infolabel.text().endswith("result4.png")


def test_second_request_while_busy_is_rejected(window, make_png):
    window.model_Box.setCurrentIndex(4)
    window.img1_text.setPlainText(str(make_png()))
    window.pwn()
    window.pwn()  # 立刻再点一次
    assert "上一个任务还在运行" in window.info_text.toPlainText()
    wait_idle(window)


def test_quick_action_without_image(window):
    window.qrcode("")
    assert "当前没有图片" in window.info_text.toPlainText()


def test_reset_clears_inputs(window):
    window.img1_text.setPlainText("a")
    window.img2_text.setPlainText("b")
    window.reset()
    assert window.img1_text.toPlainText() == ""
    assert window.img2_text.toPlainText() == ""


def test_preview_keeps_aspect_ratio(window, make_png):
    from PyQt5 import QtCore

    path = make_png(size=(320, 40))
    window.show_preview(path)
    pixmap = window.imglabel.pixmap()
    assert not pixmap.isNull()
    assert window.infolabel.text() == str(path)
    # 保持宽高比：缩放后的比例应与原图一致
    ratio = pixmap.width() / pixmap.height()
    assert abs(ratio - 8.0) < 0.05
    assert pixmap.width() <= window.imglabel.width() + 1
    del QtCore


def test_close_event_blocked_while_busy(window, make_png):
    window.model_Box.setCurrentIndex(4)
    window.img1_text.setPlainText(str(make_png()))
    window.pwn()
    window.close()
    assert "请等待结束后再关闭" in window.info_text.toPlainText()
    wait_idle(window)
