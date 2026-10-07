"""Editable Matplotlib documents, artist properties and bounded undo history."""
from __future__ import annotations

import copy
import io
import json
import pickle
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.collections import Collection, PathCollection, LineCollection
from matplotlib.figure import Figure
from matplotlib.image import AxesImage
from matplotlib.legend import Legend
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle, Ellipse
from matplotlib.text import Text, Annotation
from matplotlib.transforms import ScaledTranslation

plt.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42,
                    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Microsoft YaHei", "DejaVu Sans"]})
VERSION = "1.0.0"


def identity(artist):
    if not hasattr(artist, "_sfs_id"):
        artist._sfs_id = uuid.uuid4().hex
    return artist._sfs_id


def title_of(artist):
    if isinstance(artist, Figure): return "画布"
    if isinstance(artist, Axes): return "绘图区"
    if isinstance(artist, Legend): return "图例"
    if isinstance(artist, Text):
        return "文字：" + (artist.get_text().replace("\n", " ")[:45] or "（空）")
    label = artist.get_label() if hasattr(artist, "get_label") else ""
    return type(artist).__name__ + (f"：{label}" if label and not str(label).startswith("_") else "")


@dataclass
class Node:
    key: str
    parent: str
    title: str
    artist: Artist | None


def catalog(fig):
    """Include primitive artists, labels, ticks, legends, tables and colorbar axes."""
    nodes, seen = [], set()
    def add(artist, parent, label=None):
        if id(artist) in seen: return identity(artist)
        seen.add(id(artist))
        key = identity(artist)
        nodes.append(Node(key, parent, label or title_of(artist), artist))
        return key
    def add_legend(legend, parent):
        lr = add(legend, parent, "图例")
        add(legend.get_title(), lr, "图例标题")
        add(legend.get_frame(), lr, "图例背景与边框")
        for i, text in enumerate(legend.get_texts()): add(text, lr, f"图例文字 {i + 1}: {text.get_text()}")
        for i, handle in enumerate(legend.legend_handles):
            if handle is not None: add(handle, lr, f"图例示意 {i + 1}")
    root = add(fig, "")
    add(fig.patch, root, "画布背景")
    for index, ax in enumerate(fig.axes):
        axis_root = add(ax, root, f"绘图区 {index + 1}")
        add(ax.patch, axis_root, "绘图区背景")
        for item, name in [(ax.title, "标题"), (ax._left_title, "左标题"),
                           (ax._right_title, "右标题"), (ax.xaxis.label, "横轴标题"),
                           (ax.yaxis.label, "纵轴标题")]:
            add(item, axis_root, name + "：" + item.get_text().replace("\n", " ")[:35])
        for axis, name in [(ax.xaxis, "横轴"), (ax.yaxis, "纵轴")]:
            ar = add(axis, axis_root, name + "刻度与网格")
            add(axis.get_offset_text(), ar, "科学计数偏移")
            for i, tick in enumerate(axis.get_major_ticks() + axis.get_minor_ticks()):
                for item, role in [(tick.label1, "刻度文字"), (tick.label2, "对侧刻度文字"),
                                   (tick.tick1line, "刻度线"), (tick.tick2line, "对侧刻度线"),
                                   (tick.gridline, "网格线")]:
                    add(item, ar, f"{role} {i + 1}" + (": " + item.get_text() if isinstance(item, Text) else ""))
        for name, spine in ax.spines.items(): add(spine, axis_root, "边框：" + name)
        for item in [*ax.lines, *ax.patches, *ax.collections, *ax.images, *ax.texts, *ax.artists, *ax.tables]:
            if isinstance(item, Legend): continue
            item_root = add(item, axis_root)
            if isinstance(item, Annotation) and item.arrow_patch:
                add(item.arrow_patch, item_root, "注释箭头")
            if hasattr(item, "get_celld"):
                for position, cell in item.get_celld().items():
                    cr = add(cell, item_root, f"单元格 {position}")
                    add(cell.get_text(), cr)
        legend = ax.get_legend()
        if legend: add_legend(legend, axis_root)
    for artist in [*fig.texts, *fig.artists, *fig.patches, *fig.lines, *fig.images]:
        if isinstance(artist, Legend): continue
        add(artist, root)
    for legend in fig.legends: add_legend(legend, root)
    return nodes

def plain_color(value):
    try: return matplotlib.colors.to_hex(value, keep_alpha=True)
    except (ValueError, TypeError): return str(value)


def artist_bounds(artist, fig):
    if isinstance(artist, PathCollection):
        points = artist.get_offset_transform().transform(artist.get_offsets())
        points = points[np.isfinite(points).all(axis=1)]
        if len(points):
            radius = math_sqrt_max(artist.get_sizes()) * fig.dpi / 72 / 2
            from matplotlib.transforms import Bbox
            return Bbox.from_extents(*(points.min(axis=0) - radius), *(points.max(axis=0) + radius))
    return artist.get_window_extent(fig.canvas.get_renderer())


def math_sqrt_max(values): return float(np.sqrt(max(values))) if len(values) else 3.0


def position_mm(artist, fig):
    if isinstance(artist, Text):
        point = artist.get_transform().transform(artist.get_position())
        return fig.transFigure.inverted().transform(point) * np.asarray(fig.get_size_inches()) * 25.4
    bbox = artist_bounds(artist, fig)
    point = fig.transFigure.inverted().transform((bbox.x0, bbox.y0))
    return point * np.asarray(fig.get_size_inches()) * 25.4


def properties(artist, fig):
    """key, readable label, type, current value; only exposed setters are applied."""
    result = []
    def field(key, label, typ, value): result.append((key, label, typ, value))
    if isinstance(artist, Figure):
        w, h = artist.get_size_inches() * 25.4
        field("width_mm", "画布宽度 mm", "float", w)
        field("height_mm", "画布高度 mm", "float", h)
        field("facecolor", "背景色", "color", plain_color(artist.get_facecolor()))
        field("export_dpi", "输出分辨率 DPI", "int", getattr(artist, "_sfs_export_dpi", 600))
        return result
    field("visible", "可见", "bool", artist.get_visible())
    field("alpha", "不透明度 0–1", "float", artist.get_alpha() if artist.get_alpha() is not None else 1)
    field("zorder", "图层顺序", "float", artist.get_zorder())
    if isinstance(artist, Axes):
        x, y, w, h = artist.get_position().bounds
        fw, fh = fig.get_size_inches() * 25.4
        for key, label, value in [("left_mm", "左边位置 mm", x * fw), ("bottom_mm", "下边位置 mm", y * fh),
                                  ("width_mm", "宽度 mm", w * fw), ("height_mm", "高度 mm", h * fh)]: field(key, label, "float", value)
        for key, label, value in [("title", "标题", artist.get_title()), ("xlabel", "横轴标题", artist.get_xlabel()),
                                  ("ylabel", "纵轴标题", artist.get_ylabel())]: field(key, label, "text", value)
        for key, label, value in [("xmin", "横轴下限", artist.get_xlim()[0]), ("xmax", "横轴上限", artist.get_xlim()[1]),
                                  ("ymin", "纵轴下限", artist.get_ylim()[0]), ("ymax", "纵轴上限", artist.get_ylim()[1])]: field(key, label, "float", value)
        field("xscale", "横轴尺度", "choice:linear,log,symlog", artist.get_xscale())
        field("yscale", "纵轴尺度", "choice:linear,log,symlog", artist.get_yscale())
        field("facecolor", "绘图区底色", "color", plain_color(artist.get_facecolor()))
        field("xtick_labels", "横轴刻度文字（每行一项）", "lines", "\n".join(t.get_text() for t in artist.get_xticklabels()))
        field("ytick_labels", "纵轴刻度文字（每行一项）", "lines", "\n".join(t.get_text() for t in artist.get_yticklabels()))
        field("tick_size", "刻度字号 pt", "float", artist.get_xticklabels()[0].get_fontsize() if artist.get_xticklabels() else 7)
        field("grid_x", "横向坐标网格", "bool", any(t.get_visible() for t in artist.get_xgridlines()))
        field("grid_y", "纵向坐标网格", "bool", any(t.get_visible() for t in artist.get_ygridlines()))
        return result
    if isinstance(artist, Legend):
        xy = position_mm(artist, fig)
        field("x_mm", "图例左边 mm", "float", xy[0]); field("y_mm", "图例下边 mm", "float", xy[1])
        field("title", "图例标题", "text", artist.get_title().get_text())
        field("labels", "图例项目（每行一项）", "lines", "\n".join(t.get_text() for t in artist.get_texts()))
        field("ncols", "列数", "int", artist._ncols)
        field("font_size", "图例字号 pt", "float", artist.get_texts()[0].get_fontsize() if artist.get_texts() else 7)
        field("title_size", "标题字号 pt", "float", artist.get_title().get_fontsize())
        for key, label in [("handlelength", "示意色块长度"), ("handleheight", "示意色块高度"),
                           ("handletextpad", "示意与文字间距"), ("columnspacing", "列间距"),
                           ("labelspacing", "行间距")]: field(key, label, "float", getattr(artist, key))
        field("frame", "图例边框", "bool", artist.get_frame_on())
        return result
    if isinstance(artist, Text):
        field("text", "文字内容", "text", artist.get_text())
        field("font_size", "字号 pt", "float", artist.get_fontsize())
        field("font_family", "字体", "str", artist.get_fontfamily()[0])
        field("font_weight", "字重", "choice:normal,bold,light", artist.get_fontweight())
        field("font_style", "字形", "choice:normal,italic,oblique", artist.get_fontstyle())
        field("color", "文字颜色", "color", plain_color(artist.get_color()))
        field("rotation", "旋转角度", "float", artist.get_rotation())
        field("ha", "水平对齐", "choice:left,center,right", artist.get_ha())
        field("va", "垂直对齐", "choice:top,center,bottom,baseline,center_baseline", artist.get_va())
        xy = position_mm(artist, fig)
        field("x_mm", "文字锚点 X mm", "float", xy[0]); field("y_mm", "文字锚点 Y mm", "float", xy[1])
        return result
    if isinstance(artist, Axis):
        field("labelpad", "标题间距 pt", "float", artist.labelpad)
        return result
    if isinstance(artist, Line2D):
        field("color", "线条颜色", "color", plain_color(artist.get_color()))
        field("linewidth", "线宽 pt", "float", artist.get_linewidth())
        field("linestyle", "线型", "choice:-,--,-.,:,None", artist.get_linestyle())
        field("marker", "标记", "str", artist.get_marker())
        field("markersize", "标记大小 pt", "float", artist.get_markersize())
        field("markerfacecolor", "标记填充色", "color", plain_color(artist.get_markerfacecolor()))
        field("markeredgecolor", "标记边缘色", "color", plain_color(artist.get_markeredgecolor()))
        field("label", "系列名称", "str", artist.get_label())
    elif isinstance(artist, Patch):
        for key, label, value in [("facecolor", "填充色", plain_color(artist.get_facecolor())),
                                  ("edgecolor", "边框色", plain_color(artist.get_edgecolor())),
                                  ("linewidth", "边框线宽 pt", artist.get_linewidth()),
                                  ("hatch", "纹理 / \\ xx ..", artist.get_hatch() or "")]:
            field(key, label, "float" if key == "linewidth" else "str" if key == "hatch" else "color", value)
        if isinstance(artist, Rectangle):
            for key, label, value in [("x", "X（对象坐标）", artist.get_x()), ("y", "Y（对象坐标）", artist.get_y()),
                                      ("width", "宽度（对象坐标）", artist.get_width()), ("height", "高度（对象坐标）", artist.get_height()),
                                      ("angle", "旋转角度", artist.get_angle())]: field(key, label, "float", value)
        elif isinstance(artist, Ellipse):
            for key, label, value in [("center_x", "中心 X", artist.center[0]), ("center_y", "中心 Y", artist.center[1]),
                                      ("width", "宽度", artist.width), ("height", "高度", artist.height),
                                      ("angle", "旋转角度", artist.angle)]: field(key, label, "float", value)
    elif isinstance(artist, Collection):
        colors = artist.get_facecolors()
        edges = artist.get_edgecolors()
        field("facecolor", "填充色（整个系列）", "color", plain_color(colors[0]) if len(colors) else "none")
        field("edgecolor", "边缘色（整个系列）", "color", plain_color(edges[0]) if len(edges) else "none")
        widths = artist.get_linewidths()
        field("linewidth", "线宽 pt", "float", widths[0] if len(widths) else 1)
        if isinstance(artist, PathCollection):
            sizes = artist.get_sizes()
            field("size", "散点面积 pt²", "float", sizes[0] if len(sizes) else 25)
    if isinstance(artist, AxesImage) or (isinstance(artist, Collection) and artist.get_array() is not None):
        field("cmap", "颜色映射", "str", artist.get_cmap().name)
        field("vmin", "颜色下限", "float", artist.get_clim()[0])
        field("vmax", "颜色上限", "float", artist.get_clim()[1])
    if isinstance(artist, AxesImage):
        field("interpolation", "插值", "choice:nearest,bilinear,bicubic,none", artist.get_interpolation())
    return result


def tick_owner(text, fig):
    for ax in fig.axes:
        for axis in [ax.xaxis, ax.yaxis]:
            ticks = axis.get_major_ticks() + axis.get_minor_ticks()
            for i, tick in enumerate(ticks):
                if text in (tick.label1, tick.label2): return ax, axis, i
    return None


def freeze_tick(text, fig):
    """Moving a tick turns its presentation into a free text, keeping its tick."""
    legends = [*fig.legends, *(ax.get_legend() for ax in fig.axes if ax.get_legend())]
    controlled = tick_owner(text, fig) or any(text in [legend.get_title(), *legend.get_texts()] for legend in legends)
    if not controlled: return text
    xy = fig.transFigure.inverted().transform(text.get_transform().transform(text.get_position()))
    free = fig.text(*xy, text.get_text(), fontproperties=copy.copy(text.get_fontproperties()),
                    color=text.get_color(), ha=text.get_ha(), va=text.get_va(), rotation=text.get_rotation())
    free._sfs_id = identity(text)
    text._sfs_id = uuid.uuid4().hex
    text.set_visible(False)
    return free


def place_text(text, fig, x_mm, y_mm):
    text = freeze_tick(text, fig)
    fw, fh = fig.get_size_inches() * 25.4
    xy = (x_mm / fw, y_mm / fh)
    if isinstance(text, Annotation):
        text.set_anncoords("figure fraction")
        text.set_position(xy)
        return text
    for ax in fig.axes:
        if text in [ax.title, ax._left_title, ax._right_title]: ax._autotitlepos = False
        for axis in (ax.xaxis, ax.yaxis):
            if text is axis.label:
                axis.set_label_coords(*xy, transform=fig.transFigure)
                return text
    text.set_transform(fig.transFigure)
    text.set_position(xy)
    return text


def place_legend(legend, fig, x_mm, y_mm):
    fw, fh = fig.get_size_inches() * 25.4
    legend.set_loc("lower left")
    legend.borderaxespad = 0
    legend.set_bbox_to_anchor((x_mm / fw, y_mm / fh), transform=fig.transFigure)


def rebuild_legend(legend, fig, values):
    text_styles = [(copy.copy(t.get_fontproperties()), t.get_color()) for t in legend.get_texts()]
    title_style, title_color = copy.copy(legend.get_title().get_fontproperties()), legend.get_title().get_color()
    frame_style = {key: getattr(legend.get_frame(), "get_" + key)() for key in ("facecolor", "edgecolor", "linewidth", "alpha")}
    old = dict((key, value) for key, _, _, value in properties(legend, fig))
    old.update(values)
    labels = old["labels"].splitlines()
    handles = list(legend.legend_handles)
    if len(labels) != len(handles): raise ValueError("图例文字行数应与示意项目数一致。")
    key = identity(legend)
    owner = legend.axes if legend.axes is not None else fig
    legend.remove()
    new = owner.legend(handles, labels, title=old["title"], ncols=int(old["ncols"]),
                       fontsize=old["font_size"], title_fontsize=old["title_size"],
                       frameon=old["frame"], handlelength=old["handlelength"], handleheight=old["handleheight"],
                       handletextpad=old["handletextpad"], columnspacing=old["columnspacing"], labelspacing=old["labelspacing"])
    new._sfs_id = key
    for text, (font, color) in zip(new.get_texts(), text_styles):
        if "font_size" in values: font.set_size(values["font_size"])
        text.set_fontproperties(font); text.set_color(color)
    if "title_size" in values: title_style.set_size(values["title_size"])
    new.get_title().set_fontproperties(title_style); new.get_title().set_color(title_color)
    for key, value in frame_style.items(): getattr(new.get_frame(), "set_" + key)(value)
    place_legend(new, fig, old["x_mm"], old["y_mm"])
    for k in ("visible", "alpha", "zorder"):
        if k in old: getattr(new, "set_" + k)(old[k])
    return new


def apply_properties(artist, fig, values):
    if isinstance(artist, Legend): return rebuild_legend(artist, fig, values)
    if isinstance(artist, Figure):
        w, h = fig.get_size_inches() * 25.4
        w, h = values.get("width_mm", w), values.get("height_mm", h)
        if w <= 0 or h <= 0: raise ValueError("画布尺寸必须大于零。")
        fig.set_size_inches(w / 25.4, h / 25.4, forward=False)
        fig._sfs_size_inches = tuple(fig.get_size_inches())
        if "facecolor" in values: fig.set_facecolor(values["facecolor"])
        if "export_dpi" in values:
            if values["export_dpi"] <= 0: raise ValueError("输出分辨率必须大于零。")
            fig._sfs_export_dpi = int(values["export_dpi"])
        return artist
    if isinstance(artist, Axes):
        x, y, w, h = artist.get_position().bounds
        fw, fh = fig.get_size_inches() * 25.4
        artist.set_position([values.get("left_mm", x * fw) / fw, values.get("bottom_mm", y * fh) / fh,
                             values.get("width_mm", w * fw) / fw, values.get("height_mm", h * fh) / fh])
        if values.get("width_mm", w * fw) <= 0 or values.get("height_mm", h * fh) <= 0:
            raise ValueError("绘图区尺寸必须大于零。")
        for key in ("title", "xlabel", "ylabel", "xscale", "yscale", "facecolor"):
            if key in values: getattr(artist, "set_" + key)(values[key])
        if "xmin" in values or "xmax" in values: artist.set_xlim(values.get("xmin", artist.get_xlim()[0]), values.get("xmax", artist.get_xlim()[1]))
        if "ymin" in values or "ymax" in values: artist.set_ylim(values.get("ymin", artist.get_ylim()[0]), values.get("ymax", artist.get_ylim()[1]))
        for prefix in ("x", "y"):
            key = prefix + "tick_labels"
            if key in values:
                labels = values[key].splitlines()
                ticks = getattr(artist, "get_" + prefix + "ticks")()
                if len(labels) != len(ticks): raise ValueError("刻度文字的行数必须与刻度数相同。")
                getattr(artist, "set_" + prefix + "ticks")(ticks, labels)
            if "grid_" + prefix in values: artist.grid(values["grid_" + prefix], axis=prefix)
        if "tick_size" in values: artist.tick_params(labelsize=values["tick_size"])
        excluded = {key for key, _, _, _ in properties(artist, fig)} - {"visible", "alpha", "zorder"}
    else: excluded = set()
    if isinstance(artist, Text):
        legends = [*fig.legends, *(ax.get_legend() for ax in fig.axes if ax.get_legend())]
        title_legend = next((legend for legend in legends if artist is legend.get_title()), None)
        if "text" in values and tick_owner(artist, fig):
            _, axis, index = tick_owner(artist, fig)
            ticks = axis.get_majorticklocs()
            labels = [item.get_text() for item in axis.get_ticklabels()]
            if index < len(labels):
                labels[index] = values["text"]
                axis.set_ticks(ticks, labels=labels)
        else:
            if "text" in values:
                if title_legend: title_legend.set_title(values["text"])
                else: artist.set_text(values["text"])
        for key, setter in [("font_size", "set_fontsize"), ("font_family", "set_fontfamily"),
                            ("font_weight", "set_fontweight"), ("font_style", "set_fontstyle"),
                            ("color", "set_color"), ("rotation", "set_rotation"), ("ha", "set_ha"), ("va", "set_va")]:
            if key in values: getattr(artist, setter)(values[key])
        if "x_mm" in values or "y_mm" in values:
            x, y = position_mm(artist, fig)
            artist = place_text(artist, fig, values.get("x_mm", x), values.get("y_mm", y))
        excluded.update({"text", "font_size", "font_family", "font_weight", "font_style", "color", "rotation", "ha", "va", "x_mm", "y_mm"})
    if isinstance(artist, Ellipse) and ("center_x" in values or "center_y" in values):
        artist.center = (values.get("center_x", artist.center[0]), values.get("center_y", artist.center[1]))
        excluded.update({"center_x", "center_y"})
    if isinstance(artist, Axis) and "labelpad" in values:
        artist.labelpad = values["labelpad"]; excluded.add("labelpad")
    if isinstance(artist, PathCollection) and "size" in values:
        artist.set_sizes([values["size"]]); excluded.add("size")
    if "vmin" in values or "vmax" in values:
        lo, hi = artist.get_clim()
        artist.set_clim(values.get("vmin", lo), values.get("vmax", hi))
        excluded.update({"vmin", "vmax"})
    for key, value in values.items():
        if key in excluded: continue
        setter = getattr(artist, "set_" + key, None)
        if setter: setter(value)
    return artist


def move_artist(artist, fig, dx_px, dy_px):
    if isinstance(artist, Figure) or isinstance(artist, Axis): return artist
    dx, dy = dx_px / fig.bbox.width, dy_px / fig.bbox.height
    if isinstance(artist, Axes):
        x, y, w, h = artist.get_position().bounds
        artist.set_position([x + dx, y + dy, w, h])
    elif isinstance(artist, Legend):
        x, y = position_mm(artist, fig)
        fw, fh = fig.get_size_inches() * 25.4
        place_legend(artist, fig, x + dx * fw, y + dy * fh)
    elif isinstance(artist, Text):
        x, y = position_mm(artist, fig)
        fw, fh = fig.get_size_inches() * 25.4
        artist = place_text(artist, fig, x + dx * fw, y + dy * fh)
    elif isinstance(artist, Collection):
        if isinstance(artist, PathCollection):
            artist.set_offset_transform(artist.get_offset_transform() + ScaledTranslation(dx, dy, fig.transFigure))
        else: artist.set_transform(artist.get_transform() + ScaledTranslation(dx, dy, fig.transFigure))
    else:
        artist.set_transform(artist.get_transform() + ScaledTranslation(dx, dy, fig.transFigure))
    return artist


class Document:
    def __init__(self, figures=None, names=None):
        self.figures = figures or []
        self.names = names or [f"图 {i + 1}" for i in range(len(self.figures))]
        self.active = 0
        self.selected = []
        self.path = None
        self.metadata = {"app_version": VERSION, "export_dpi": 600, "source": ""}
        self.past, self.future = [], []
        self.dirty = False
        for fig in self.figures: self.prepare(fig)

    @staticmethod
    def prepare(fig):
        if not hasattr(fig, "_sfs_size_inches"): fig._sfs_size_inches = tuple(fig.get_size_inches())
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        FigureCanvasAgg(fig).draw()
        catalog(fig)

    @property
    def figure(self): return self.figures[self.active] if self.figures else None

    def normalize(self):
        for fig in self.figures:
            if hasattr(fig, "_sfs_size_inches"): fig.set_size_inches(fig._sfs_size_inches, forward=False)

    def capture(self):
        self.normalize()
        return pickle.dumps({"figures": self.figures, "names": self.names, "active": self.active,
                             "selected": self.selected, "metadata": self.metadata}, protocol=5)

    def restore(self, data):
        state = pickle.loads(data)
        for fig in self.figures: plt.close(fig)
        for key, value in state.items(): setattr(self, key, value)
        for fig in self.figures: self.prepare(fig)
        self.dirty = True

    def remember(self, snapshot):
        self.past.append(snapshot)
        self.future.clear()
        while len(self.past) > 40 or (len(self.past) > 1 and sum(map(len, self.past)) > 64 * 1024 ** 2):
            self.past.pop(0)
        self.dirty = True

    def change(self, action):
        before = self.capture()
        try: result = action()
        except Exception:
            self.restore(before)
            raise
        self.remember(before)
        return result

    def undo(self):
        if not self.past: return False
        self.future.append(self.capture())
        self.restore(self.past.pop())
        return True

    def redo(self):
        if not self.future: return False
        self.past.append(self.capture())
        self.restore(self.future.pop())
        return True

    def nodes(self): return catalog(self.figure) if self.figure else []

    def lookup(self, key):
        return next((node.artist for node in self.nodes() if node.key == key), None)

    def save(self, path):
        path = Path(path)
        self.normalize()
        # Zip compression keeps repeated coordinates and image arrays compact.
        temp = path.with_suffix(path.suffix + ".tmp")
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as package:
            package.writestr("manifest.json", json.dumps({"format": "ScientificFigureStudio", "version": 1,
                                                          "names": self.names, "metadata": self.metadata}, ensure_ascii=False, default=str))
            package.writestr("document.pkl", self.capture())
        temp.replace(path)
        self.path, self.dirty = path, False

    @classmethod
    def open(cls, path):
        with zipfile.ZipFile(path) as package:
            manifest = json.loads(package.read("manifest.json"))
            if manifest.get("format") != "ScientificFigureStudio": raise ValueError("不是本工具的科研图像项目。")
            state = pickle.loads(package.read("document.pkl"))
        doc = cls(state["figures"], state["names"])
        doc.active, doc.selected, doc.metadata = state["active"], state["selected"], state["metadata"]
        doc.path = Path(path)
        return doc

    def export(self, path, dpi=None, transparent=False):
        self.normalize()
        plt.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42})
        if dpi is None: dpi = getattr(self.figure, "_sfs_export_dpi", 600)
        kwargs = {"dpi": dpi, "transparent": transparent}
        if Path(path).suffix.lower() in {".tif", ".tiff"}: kwargs["pil_kwargs"] = {"compression": "tiff_lzw"}
        self.figure.savefig(path, **kwargs)
