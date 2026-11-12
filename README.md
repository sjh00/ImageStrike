## 🎈简介

ImageStrike 是一款用于 CTF 图片隐写的综合利用工具，基于 PyQt5。

本仓库基于 [zR00t1/ImageStrike](https://github.com/zR00t1/ImageStrike) V0.2（2022 年）做了现代环境适配：
原版在 Python 3.11+ / NumPy 2 / 新版 Pillow 上已经跑不起来（多处直接崩溃），
这次把依赖、算法兼容性、外部工具的调用方式都修了一遍，并补了 111 条自动化测试。

<img src="imgs/1.png" style="zoom:60%;" />

## 🎗️环境依赖

| 依赖 | 说明 |
| --- | --- |
| Python ≥ 3.10 | 已在 3.14 上验证；用 [uv](https://docs.astral.sh/uv/) 管理 |
| PyQt5 / Pillow / NumPy / cryptography / zxing-cpp | 由 `uv sync` 自动安装 |
| pyexiv2（可选） | 更完整的 EXIF/IPTC/XMP 读取，缺失时回退到 Pillow |
| Java（可选） | 只有 F5 隐写需要 |
| `tools/` 下的 exe | pngcheck / steghide / foremost，仓库自带 |

原版要求安装 **Visual C++ 2013 运行库**，那是 pyexiv2 1.x 的依赖。
现在 pyexiv2 改为可选依赖，一般无需单独安装；若读取元数据时报 DLL 缺失，
装一下 [VC++ 2015-2022 运行库](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) 即可。

## 🚀安装与运行

双击 **`ImageStrike.bat`** 即可启动：它会自动切到程序目录、用 uv 同步依赖、
再打开图形界面。首次运行需要联网下载依赖（约 60MB，主要是 PyQt5），之后离线可用。

命令行里也可以直接用它，参数会透传给主程序：

```bat
ImageStrike.bat                    :: 图形界面
ImageStrike.bat --list             :: 查看全部功能编号
ImageStrike.bat --cli 6 broken.png :: 编号 6：PNG 改宽高
ImageStrike.bat --cli 1 cover.png marked.png   :: 编号 1：盲水印
```

程序退出码非 0 时窗口会停住并显示原因（按任意键关闭），所以双击运行出错不会一闪而过。

不用 bat、直接用 uv 也可以：

```bash
uv sync                    # 创建 .venv 并安装依赖
uv run python ImageStrike.py          # 图形界面
uv run python ImageStrike.py --cli 6 broken.png
```

想彻底不弹控制台窗口，把 `ImageStrike.bat` 里的 `python.exe` 换成 `pythonw.exe` 即可
（代价是启动报错时看不到信息）。

不想用 uv 也可以：`pip install -e .` 或用任意 Python ≥3.10 安装
`pyqt5==5.15.11`、`pyqt5-qt5==5.15.2`（Windows 必须锁这个版本，新的 5.15.19 不再提供 Windows wheel）、
`pillow`、`numpy`、`cryptography`、`zxing-cpp`。

## 🏷️功能一览

下拉框编号 = `--cli` 的编号，定义在 [strike/jobs.py](strike/jobs.py) 的 `MODES` 里（界面选项由它生成，不会走样）。

| # | 功能 | 输入 | 输出 |
| --- | --- | --- | --- |
| 0 | All in One 一键巡检 | Img1 文件 | 元数据 + 二维码 + strings + 结构检查 + stegpy 探测 |
| 1 | 盲水印（旧版种子 oldseed） | Img1 原图、Img2 加密图 | `imgs/result1.png` |
| 2 | 盲水印（新版种子） | 同上 | `imgs/result2.png` |
| 3 | 二维码扫描 | Img1 图片 | 识别内容 |
| 4 | 图片反相 | Img1 图片 | `imgs/result4.png` |
| 5 | RGB → 图片 | Img1 txt（每行 `R G B`） | `imgs/result5.png` |
| 6 | PNG 改宽高 | Img1 png | `imgs/result6.png` |
| 7 | PNG IDAT 检测 | Img1 png | pngcheck 原始输出 |
| 8 | 图片元数据 | Img1 图片 | EXIF / IPTC / XMP |
| 9 | Gif 帧分离 | Img1 gif | `imgs/gif/frame*.png` |
| 10 | F5 隐写 | Img1 文件，Img2 密码（默认 abc123） | 提取内容 |
| 11 | Strings 可打印字符 | Img1 任意文件 | 带十六进制偏移的字符串 |
| 12 | JPG 改高度（×2） | Img1 jpg | `imgs/result12.jpg` |
| 13 | JPG 改宽度（×2） | Img1 jpg | `imgs/result13.jpg` |
| 14 | 二进制 → 黑白矩阵 | Img1 txt（0/1） | `imgs/result14.png` |
| 15 | Stegpy（stegv3） | Img1 文件，Img2 密码 | 文本或 `imgs/stegpy_out/` |
| 16 | Steghide | Img1 文件，Img2 密码 | `imgs/steghide_out/` |
| 17 | Foremost | Img1 任意文件 | `imgs/foremost_out/` |

界面上：双击 Img1/Img2 路径框可直接选文件，也可以把文件拖进窗口；
输出区右键可复制/清空；预览区右键可打开图片、扫二维码、反相、清空。

## 🔧这一版改了什么

### 跑不起来的问题（致命）

- `random.shuffle(m, random=random.random)` 的 `random` 参数在 **Python 3.11 被删除**，
  盲水印一执行就 `TypeError`。按 3.10 及以前的分支逻辑重新实现，
  并用 CPython 3.10 实跑的结果做了逐字节比对（`tests/test_watermark.py`）。
- `np.uint8(负数)` 在 **NumPy 2** 抛 `OverflowError`，盲水印对负数像素必崩。改为等价的
  “截断取整 + 取低 8 位”，与原来的 C 转换语义一致。
- 盲水印原来用 `cv2.imdecode(..., IMREAD_UNCHANGED)` 读取：灰度图得到二维数组能算，
  彩色图得到三维数组后 `np.uint8(向量)` 直接抛异常——**原版实际只支持灰度图**。现在彩色图按通道并行处理。
- `gmpy2` 在 Windows 上要编译，改为标准库 `math.isqrt`。
- `from gmpy2 import iroot` / `import cv2.cv2` / `pyzbar.pyzbar as pyzbar` 都是旧写法或硬导入，
  任一依赖缺失整个程序都起不来。现在改为按需导入，并且不再需要 OpenCV（省 40MB+）。

### 功能实际不可用的问题

- **Foremost 从来没有真正跑通过**：仓库只带了 `foremost.exe` 没带 `foremost.conf`，
  程序会去 `C:\Program Files\foremost\` 找配置然后直接退出；即使给了配置，
  原脚本用的 `-T`（加时间戳）会让这个 Windows 构建一个文件都不恢复，
  `-q` 又只在 512 字节边界搜索会漏掉非对齐的嵌入文件。现在自带配置、去掉 `-T`/`-q`。
- **Steghide 有密码时几乎必然误判**：原脚本把整段填充数据当成 Fernet token 解密。
  stegpy 的 `stegv3` 提取同理，现在会试探合法的 token 边界；另外 wav/gif 分支原本缺
  `header, data = content`，直接 `NameError`。
- **Steghide 不再是“仅支持有密码”**：密码留空时会先试空口令，再提示。
- **PNG 改宽高**：除了原来的 CRC 爆破，新增“改宽高时把 CRC 也算对了”的处理路径
  （按 IDAT 解压长度反推，候选不唯一时全部列出来，可用 `target_size` 指定）。
- **JPG 改宽高**：原来是“整文件转 hex 再字符串替换”，可能替换到别处的字节；
  改为解析 SOF 段直接改写，且支持带 EXIF 段的 JPEG。宽、高分别输出
  `result12.jpg` / `result13.jpg`（原来两者共用 result12）。
- **All in One 原本是空的**：选它什么都不会发生（`pwn()` 里没有 index 0 分支）。
  现在会做一遍快速只读巡检。

### 稳定性与体验

- 所有外部程序调用从 `shell=True` + 字符串拼接改为参数列表：路径含空格/中文/`&` 不再出错，
  GUI 下也不再闪黑框，并统一加了超时。
- 所有相对路径改为基于程序目录解析，从任意工作目录启动都能找到 `imgs/` 和 `tools/`。
- 耗时操作（PNG 爆破、foremost、F5…）放到子线程，界面不再假死；运行中禁止重复提交。
- 输出区只读 + 等宽字体 + 按 `[+]`/`[!]`/`[*]` 着色，限制最大行数避免内存膨胀。
- 输入框忽略 `file:///` 前缀、引号、百分号转义和多行粘贴。
- 高 DPI 支持；预览保持宽高比（原版 `setScaledContents(True)` 会拉变形）。
- 二维码识别引擎从停更的 pyzbar 换成仍在维护的 **zxing-cpp**，识别失败时自动做灰度/增强/放大重试。
- `logo.ico`、`widgets_zh_CN.qm` 缺失时不再报错（原版引用了仓库里不存在的文件）。

## 🧪测试

```bash
uv run pytest            # 111 条用例，约 2 秒
```

覆盖：盲水印与 CPython 3.10 的逐字节一致性、PNG/JPEG 宽高修复、各类图片运算、
strings 偏移、stegpy 三种比特深度与密码路径、steghide/foremost/F5 的真实往返调用、
调度层、以及 offscreen 模式下的界面接线（下拉框同步、线程、预览、关闭拦截）。

## ⚠️已知限制

- **F5 只验证了“非 F5 图片”这条负向路径**：仓库里没有 F5 的 Embed 工具，
  构造不出样本，所以“正确提取”没做过端到端验证。
- **stegpy 的 JPEG（DCT 系数）不支持**：新版 stegpy 对 jpg 把数据藏在 DCT 系数里，需要 jpeglib，
  遇到会明确提示改用官方 CLI。GIF 的调色板索引依赖 Pillow 的加载策略，极端样本可能对不上。
- **PNG 改宽高在“CRC 已重算”时可能有多解**：数据长度不足以唯一确定宽高，
  工具会列出全部候选并默认取面积最大的，猜错请用 `--cli` 或 API 指定尺寸。
- **盲水印的差值图本身就是那团噪声图**，需要人眼从里面看出水印，这是算法本身的性质。
- Windows 专属：`tools/` 里的 pngcheck / steghide / foremost 都是 Windows 可执行文件。

## 🔗参考

[https://github.com/chishaxie/blindwatermark](https://github.com/chishaxie/blindwatermark)

[https://github.com/dhsdshdhk/stegpy](https://github.com/dhsdshdhk/stegpy)

[https://sourceforge.net/projects/steghide/](https://sourceforge.net/projects/steghide/)

[https://github.com/Bronya-Rayi/auto-misc-pic](https://github.com/Bronya-Rayi/auto-misc-pic)

[https://github.com/RetrO-hash/CTFpics](https://github.com/RetrO-hash/CTFpics)

代码大多取自网络资料，在此表示感谢💕

## 📁目录结构

```
ImageStrike.bat    双击启动（自检依赖 + 启动界面 / 透传命令行参数）
ImageStrike.py     入口（GUI / --cli）
gui.py             图形界面（可被 offscreen 测试直接实例化）
mainUi.py          界面布局，下拉框由 strike.jobs.MODES 生成
strike/            核心逻辑，不依赖 PyQt5
  jobs.py          功能清单 MODES + 统一调度 run_job
  watermark.py     盲水印（FFT 差值）
  dimfix.py        PNG/JPEG 宽高修复
  imageops.py      反相 / RGB 转图 / 01 转图 / GIF 拆帧
  metadata.py      EXIF / IPTC / XMP
  textscan.py      带偏移的 strings
  qr.py            二维码识别
  stegtools.py     pngcheck / F5 / steghide / foremost
  stegpy_extract.py stegpy(stegv3) 提取
  proc.py          外部命令调用的公共封装
tests/             111 条 pytest 用例
tools/             pngcheck / steghide / foremost(+conf) / F5
```
