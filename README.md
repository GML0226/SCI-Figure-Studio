# Scientific Figure Studio v1.0

一个本地运行的科研图像可视化编辑工具，支持编辑 Matplotlib 图像的文字、图例、坐标轴和图形布局。

![编辑器界面](docs/editor_preview.png)

## 下载与使用

在本仓库的 **Releases** 页面下载 ScientificFigureStudio_v1.0_Windows_x64.zip。
解压后双击 ScientificFigureStudio.exe，无需安装 Python 或额外绘图软件。

- 支持 Windows 10/11 64 位，单文件程序约 42.3 MiB。
- 点击“导入”，打开 Python 绘图脚本、Excel/CSV/TSV 表格或 .sfig 项目。
- 点击图中元素，或从左侧元素树选择，修改右侧属性后点击“应用属性”。
- 拖动调整位置；Shift 拖动绘图区调整宽高；方向键微调位置。
- Ctrl+Z 撤销；Ctrl+Y 或 Ctrl+Shift+Z 重做；Ctrl+S 保存；Ctrl+E 导出。
- 便携包中的 example.sfig 和 examples/ 是通用示例。

## 功能

编辑标题、轴标题、刻度、注释、字体、颜色、位置、旋转和对齐。
编辑原生图例标题、项目文字、列数、字号、间距、边框和位置。
编辑柱子、矩形、椭圆、线条、散点、热图和色条的常用属性。
调整画布物理尺寸（mm）、绘图区比例、坐标范围和输出 DPI。
支持多选、批量修改、隐藏、删除、对齐及添加文字、图例、箭头和矩形。
保存 .sfig 项目，导出 SVG/PDF/PNG/TIFF；默认 600 dpi，SVG 文字可编辑。
历史最多 40 步，历史内存限制约 64 MiB；大型图像会保留较少步数。

## 导入与支持范围

便携版内置 Matplotlib、NumPy、openpyxl 和 Python 标准库。
支持直接运行绘图脚本，捕获 plt.show() 和 Figure.savefig() 生成的图像。
一个脚本可以包含多张图，也支持提供 build_figure() 函数并返回 Figure。
通用示例见 examples/source_template.py 和 examples/methods.csv。
数据文件及辅助 Python 文件保持原来的相对位置即可。

为控制体积，便携版不包含 pandas、SciPy、seaborn、PyTorch。
依赖其他库的脚本可改用内置库，或将数据导出为 CSV/Excel 后导入。
Python 脚本和 .sfig 项目应来自可信来源。
PNG/JPG/TIFF 导入为底图，栅格化文字和曲线仍为像素。
本版支持 SVG 导出，不支持完整 SVG 文件重新解析导入。
标准 Matplotlib 元素可编辑，第三方自定义 Artist 的特殊属性不保证支持。

## 从源码运行与构建

使用 Windows Python 3.12：

    python -m pip install -r requirements.txt
    python src/app.py

运行 build.ps1 可重新构建单文件 EXE，输出至 portable/。
构建脚本会创建独立虚拟环境并安装 PyInstaller。
普通用户运行便携 EXE 无需这些开发依赖。

## 项目结构

- src/：界面、编辑模型、导入模块和行为检查。
- assets/：程序图标。
- examples/：通用绘图源码与表格示例。
- docs/：界面预览。
- ScientificFigureStudio.spec、build.ps1：Windows 打包配置。
- requirements.txt：源码运行依赖。

便携包附带内置第三方组件的许可证文件。
