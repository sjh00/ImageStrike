# -*- coding: utf-8 -*-
"""ImageStrike 界面定义。

原文件是 pyuic5 生成的（依赖已不存在的 mainUi.ui）。这里改为手工维护：
- 下拉框选项直接来自 `strike.jobs.MODES`，界面与逻辑不会走偏；
- 图标/翻译文件缺失时静默跳过，不再指向不存在的 logo.ico；
- 日志区只读 + 等宽字体，预览区保持宽高比。
"""

from __future__ import annotations

from PyQt5 import QtCore, QtGui, QtWidgets

from strike.jobs import MODES
from strike.paths import BASE_DIR

LOG_FONT = "Consolas"


class Ui_ImageStrike(object):
    def setupUi(self, ImageStrike):
        ImageStrike.setObjectName("ImageStrike")
        ImageStrike.resize(972, 543)
        ImageStrike.setAcceptDrops(True)

        icon_path = BASE_DIR / "logo.ico"
        if icon_path.exists():
            ImageStrike.setWindowIcon(QtGui.QIcon(str(icon_path)))

        self.centralwidget = QtWidgets.QWidget(ImageStrike)
        self.centralwidget.setObjectName("centralwidget")

        # ---------------------------------------------------------- 左侧设置区
        self.setting = QtWidgets.QGroupBox(self.centralwidget)
        self.setting.setGeometry(QtCore.QRect(10, 10, 431, 201))
        self.setting.setObjectName("setting")

        self.model = QtWidgets.QLabel(self.setting)
        self.model.setGeometry(QtCore.QRect(10, 20, 71, 31))
        self.model.setObjectName("model")

        self.model_Box = QtWidgets.QComboBox(self.setting)
        self.model_Box.setGeometry(QtCore.QRect(80, 20, 341, 31))
        self.model_Box.setStyleSheet("QComboBox QAbstractItemView::item { min-height: 10px; }")
        self.model_Box.setObjectName("model_Box")
        self.model_Box.setView(QtWidgets.QListView())
        for mode in MODES:
            self.model_Box.addItem(mode.label, userData=mode.index)

        self.img1path = QtWidgets.QLabel(self.setting)
        self.img1path.setGeometry(QtCore.QRect(10, 65, 66, 31))
        self.img1path.setObjectName("img1path")

        self.img1_text = QtWidgets.QTextEdit(self.setting)
        self.img1_text.setGeometry(QtCore.QRect(80, 62, 341, 40))
        self.img1_text.setObjectName("img1_text")
        self.img1_text.setAcceptDrops(False)
        self.img1_text.setTabChangesFocus(True)

        self.img2path = QtWidgets.QLabel(self.setting)
        self.img2path.setGeometry(QtCore.QRect(10, 112, 66, 31))
        self.img2path.setObjectName("img2path")

        self.img2_text = QtWidgets.QTextEdit(self.setting)
        self.img2_text.setGeometry(QtCore.QRect(80, 110, 341, 40))
        self.img2_text.setObjectName("img2_text")
        self.img2_text.setAcceptDrops(False)
        self.img2_text.setTabChangesFocus(True)

        self.pwnButton = QtWidgets.QPushButton(self.setting)
        self.pwnButton.setGeometry(QtCore.QRect(80, 160, 101, 31))
        self.pwnButton.setObjectName("pwnButton")

        self.resetButton = QtWidgets.QPushButton(self.setting)
        self.resetButton.setGeometry(QtCore.QRect(320, 160, 101, 31))
        self.resetButton.setObjectName("resetButton")

        # ---------------------------------------------------------- 输出区
        self.info = QtWidgets.QGroupBox(self.centralwidget)
        self.info.setGeometry(QtCore.QRect(10, 220, 431, 311))
        self.info.setObjectName("info")

        self.info_text = QtWidgets.QTextEdit(self.info)
        self.info_text.setGeometry(QtCore.QRect(5, 20, 421, 286))
        self.info_text.setObjectName("info_text")
        self.info_text.setReadOnly(True)
        self.info_text.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        self.info_text.document().setMaximumBlockCount(20000)
        log_font = QtGui.QFont(LOG_FONT, 9)
        log_font.setStyleHint(QtGui.QFont.Monospace)
        self.info_text.setFont(log_font)

        # ---------------------------------------------------------- 预览区
        self.viewer = QtWidgets.QGroupBox(self.centralwidget)
        self.viewer.setGeometry(QtCore.QRect(450, 10, 511, 521))
        self.viewer.setObjectName("viewer")

        self.imglabel = QtWidgets.QLabel(self.viewer)
        self.imglabel.setGeometry(QtCore.QRect(10, 20, 491, 491))
        self.imglabel.setAlignment(QtCore.Qt.AlignCenter)
        self.imglabel.setText("")
        self.imglabel.setObjectName("imglabel")

        self.infolabel = QtWidgets.QLabel(self.viewer)
        self.infolabel.setGeometry(QtCore.QRect(10, 490, 491, 21))
        self.infolabel.setText("")
        self.infolabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.infolabel.setObjectName("infolabel")
        self.infolabel.raise_()
        self.imglabel.raise_()

        ImageStrike.setCentralWidget(self.centralwidget)

        self.retranslateUi(ImageStrike)
        QtCore.QMetaObject.connectSlotsByName(ImageStrike)
        self.model_Box.setCurrentIndex(0)

    def retranslateUi(self, ImageStrike):
        _translate = QtCore.QCoreApplication.translate
        ImageStrike.setWindowTitle(
            _translate("ImageStrike", "ImageStrike V0.3        By zR00t1")
        )
        self.setting.setTitle(_translate("ImageStrike", "设置"))
        self.img1path.setText(_translate("ImageStrike", "Img1Path："))
        self.img2path.setText(_translate("ImageStrike", "Img2Path："))
        self.model.setText(_translate("ImageStrike", "隐写方式："))
        self.pwnButton.setText(_translate("ImageStrike", "Pwn"))
        self.resetButton.setText(_translate("ImageStrike", "Reset"))
        self.info.setTitle(_translate("ImageStrike", "输出信息"))
        self.viewer.setTitle(_translate("ImageStrike", "预览"))
