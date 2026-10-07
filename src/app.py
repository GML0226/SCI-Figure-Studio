"""Scientific Figure Studio: portable local scientific figure editor."""
from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import os
import sys
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.legend import Legend
from matplotlib.text import Text
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle, Ellipse
from matplotlib.image import AxesImage

from core import Document, identity, catalog, properties, apply_properties, move_artist, artist_bounds, VERSION
from importers import blank_document, demo_document, load_python, load_image, table_preview, create_chart


BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def configure_display():
    # Avoid Windows DPI virtualization, so the full editor fits the screen and
    # pointer coordinates match the rendered Matplotlib canvas.
    if sys.platform == "win32":
        import ctypes
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError): pass


class StableCanvas(FigureCanvasTkAgg):
    def _update_device_pixel_ratio(self, event=None):
        # Preview DPI is already computed from the physical viewport pixels.
        # TkAgg's extra Windows scale factor would enlarge it a second time.
        return None

    def resize(self, event):
        size = self.figure._sfs_size_inches
        super().resize(event)
        self.figure.set_size_inches(size, forward=False)


class DataDialog(tk.Toplevel):
    def __init__(self, parent, path):
        super().__init__(parent)
        self.title("导入数据并创建科研图")
        self.geometry("760x640")
        self.transient(parent); self.grab_set()
        self.path, self.result = path, None
        self.rows, sheets = table_preview(path)
        form = ttk.Frame(self, padding=14); form.pack(fill="x")
        self.sheet = tk.StringVar(value=sheets[0] if sheets else "")
        if sheets:
            ttk.Label(form, text="工作表").grid(row=0, column=0, sticky="w")
            combo = ttk.Combobox(form, textvariable=self.sheet, values=sheets, state="readonly")
            combo.grid(row=0, column=1, sticky="ew"); combo.bind("<<ComboboxSelected>>", self.reload)
        self.kind = tk.StringVar(value="分组柱状图")
        self.category = tk.StringVar()
        self.percent = tk.BooleanVar(value=False)
        self.series_rows = tk.BooleanVar(value=False)
        self.title_text = tk.StringVar(value=Path(path).stem)
        self.ylabel = tk.StringVar(value="Value")
        for row, (label, var, options) in enumerate([
            ("图形类型", self.kind, ["分组柱状图", "横向柱状图", "折线图", "散点图"]),
            ("类别列", self.category, []),
        ], start=1):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=6)
            box = ttk.Combobox(form, textvariable=var, values=options, state="readonly", width=36)
            box.grid(row=row, column=1, sticky="ew", pady=6)
            if label == "类别列": self.category_box = box
        for row, (label, var) in enumerate([("标题", self.title_text), ("数值轴标题", self.ylabel)], start=3):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Checkbutton(form, text="将 0–1 比例乘以 100，显示百分数", variable=self.percent).grid(row=5, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Checkbutton(form, text="每行作为一个系列（例如每行一种方法）", variable=self.series_rows).grid(row=6, column=0, columnspan=2, sticky="w", pady=5)
        form.columnconfigure(1, weight=1)
        ttk.Label(self, text="选择要绘制的数值列（Ctrl 或 Shift 多选）", padding=8).pack(anchor="w")
        self.columns = tk.Listbox(self, selectmode="extended", exportselection=False, height=6)
        self.columns.pack(fill="x", padx=14)
        self.preview = ttk.Treeview(self, show="headings", height=7)
        self.preview.pack(fill="both", expand=True, padx=14, pady=10)
        buttons = ttk.Frame(self, padding=10); buttons.pack(fill="x")
        ttk.Button(buttons, text="创建图像", command=self.accept).pack(side="right")
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right", padx=8)
        self.populate()
        self.wait_window()

    def populate(self):
        headers = [str(v) if v is not None else f"列 {i + 1}" for i, v in enumerate(self.rows[0])]
        self.category_box.configure(values=[f"{i + 1}. {v}" for i, v in enumerate(headers)])
        self.category.set(f"1. {headers[0]}")
        self.columns.delete(0, "end")
        for header in headers: self.columns.insert("end", header)
        for index in range(1, len(headers)):
            numeric = False
            for row in self.rows[1:]:
                if index < len(row):
                    try: float(row[index]); numeric = True; break
                    except (TypeError, ValueError): pass
            if numeric: self.columns.selection_set(index)
        self.preview.delete(*self.preview.get_children())
        self.preview["columns"] = [str(i) for i in range(len(headers))]
        for i, name in enumerate(headers):
            self.preview.heading(str(i), text=name); self.preview.column(str(i), width=115, stretch=True)
        for row in self.rows[1:9]: self.preview.insert("", "end", values=["" if v is None else v for v in row])

    def reload(self, event=None):
        self.rows, _ = table_preview(self.path, self.sheet.get()); self.populate()

    def accept(self):
        try:
            columns = list(self.columns.curselection())
            category = int(self.category.get().split(".")[0]) - 1
            columns = [i for i in columns if i != category]
            if not columns: raise ValueError("请至少选择一个数值列。")
            self.result = create_chart(self.rows, category, columns,
                {"分组柱状图": "bar", "横向柱状图": "barh", "折线图": "line", "散点图": "scatter"}[self.kind.get()],
                self.percent.get(), self.series_rows.get(), self.title_text.get(), self.ylabel.get())
            self.result.metadata["source"] = str(self.path)
            self.destroy()
        except Exception as error: messagebox.showerror("无法创建图像", str(error), parent=self)


class App:
    def __init__(self, root, document=None, check=False):
        self.root, self.check = root, check
        self.doc = document or blank_document()
        self.canvas, self.figure_widget, self.drag = None, None, None
        self.zoom, self.pending, self.tree_lock = "fit", None, False
        self.fields = []
        self.nodes = []
        root.title("科研图像编辑器 · Scientific Figure Studio")
        icon = Path(getattr(sys, "_MEIPASS", BASE / "assets")) / "app.ico"
        if icon.exists(): root.iconbitmap(str(icon))
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        window_w, window_h = min(1460, screen_w - 60), min(900, screen_h - 100)
        root.geometry(f"{window_w}x{window_h}")
        root.minsize(min(1100, window_w), min(700, window_h))
        root.rowconfigure(1, weight=1); root.columnconfigure(0, weight=1)
        self.make_menus()
        toolbar = ttk.Frame(root, padding=(8, 7)); toolbar.grid(row=0, column=0, sticky="ew")
        for label, command in [("导入", self.open_file), ("保存项目", self.save), ("导出图像", self.export),
                               ("撤销 Ctrl+Z", self.undo), ("重做", self.redo)]:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=3)
        self.figchoice = tk.StringVar()
        self.figmenu = ttk.Combobox(toolbar, textvariable=self.figchoice, state="readonly", width=24)
        self.figmenu.pack(side="left", padx=12); self.figmenu.bind("<<ComboboxSelected>>", self.switch_figure)
        for label, command in [("适应", self.fit), ("−", lambda: self.scale(.8)), ("+", lambda: self.scale(1.25))]:
            ttk.Button(toolbar, text=label, width=5, command=command).pack(side="left", padx=2)

        panes = ttk.Panedwindow(root, orient="horizontal"); panes.grid(row=1, column=0, sticky="nsew")
        left = ttk.Frame(panes, width=245); middle = ttk.Frame(panes); right = ttk.Frame(panes, width=330)
        panes.add(left, weight=0); panes.add(middle, weight=1); panes.add(right, weight=0)
        ttk.Label(left, text="图中元素（Ctrl / Shift 多选）", padding=8).pack(anchor="w")
        self.search = tk.StringVar(); self.search.trace_add("write", lambda *a: self.refresh_tree())
        ttk.Entry(left, textvariable=self.search).pack(fill="x", padx=8)
        self.only_visible = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="仅显示可见元素", variable=self.only_visible, command=self.refresh_tree).pack(anchor="w", padx=8, pady=6)
        treebox = ttk.Frame(left); treebox.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(treebox, show="tree", selectmode="extended")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(treebox, command=self.tree.yview); scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set); self.tree.bind("<<TreeviewSelect>>", self.tree_select)

        self.viewport = tk.Canvas(middle, background="#E9EBEF", highlightthickness=0)
        self.viewport.grid(row=0, column=0, sticky="nsew")
        middle.rowconfigure(0, weight=1); middle.columnconfigure(0, weight=1)
        hs = ttk.Scrollbar(middle, orient="horizontal", command=self.viewport.xview); hs.grid(row=1, column=0, sticky="ew")
        vs = ttk.Scrollbar(middle, command=self.viewport.yview); vs.grid(row=0, column=1, sticky="ns")
        self.viewport.configure(xscrollcommand=hs.set, yscrollcommand=vs.set)
        self.viewport.bind("<Configure>", self.queue_draw)
        self.host = ttk.Frame(self.viewport)
        self.hostwindow = self.viewport.create_window(20, 20, window=self.host, anchor="nw")

        ttk.Label(right, text="元素属性", padding=8, font=("Microsoft YaHei", 11, "bold")).pack(anchor="w")
        self.selection_label = tk.StringVar(value="在图中点击，或从左侧选择元素")
        ttk.Label(right, textvariable=self.selection_label, padding=8, wraplength=310).pack(anchor="w")
        inspectorbox = ttk.Frame(right); inspectorbox.pack(fill="both", expand=True)
        self.inspector = tk.Canvas(inspectorbox, highlightthickness=0, width=325)
        self.inspector.pack(side="left", fill="both", expand=True)
        rs = ttk.Scrollbar(inspectorbox, command=self.inspector.yview); rs.pack(side="right", fill="y")
        self.inspector.configure(yscrollcommand=rs.set)
        self.property_host = ttk.Frame(self.inspector)
        self.property_window = self.inspector.create_window((0, 0), window=self.property_host, anchor="nw")
        self.property_host.bind("<Configure>", lambda e: self.inspector.configure(scrollregion=self.inspector.bbox("all")))
        self.inspector.bind("<Configure>", lambda e: self.inspector.itemconfigure(self.property_window, width=e.width))
        self.inspector.bind("<MouseWheel>", lambda e: self.inspector.yview_scroll(-int(e.delta / 120), "units"))
        ttk.Button(right, text="应用属性（一次操作，可撤销）", command=self.apply).pack(fill="x", padx=8, pady=8)
        actions = ttk.Frame(right, padding=8); actions.pack(fill="x")
        for i, (label, command) in enumerate([("添加文字", self.add_text), ("添加图例", self.add_legend),
                                            ("添加箭头", self.add_arrow), ("添加矩形", self.add_rectangle),
                                            ("隐藏 / 显示", self.toggle_visible), ("移除元素", self.remove)]):
            ttk.Button(actions, text=label, command=command).grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=3)
        actions.columnconfigure(0, weight=1); actions.columnconfigure(1, weight=1)
        self.status = tk.StringVar(value="导入 Python 绘图源文件或表格开始编辑。")
        ttk.Label(root, textvariable=self.status, padding=7, wraplength=1380).grid(row=2, column=0, sticky="ew")
        self.bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.refresh_all()

    def make_menus(self):
        menu = tk.Menu(self.root)
        file = tk.Menu(menu, tearoff=False); menu.add_cascade(label="文件", menu=file)
        for label, command in [("新建 Ctrl+N", self.new), ("导入 / 打开 Ctrl+O", self.open_file),
                               ("保存项目 Ctrl+S", self.save), ("项目另存为 Ctrl+Shift+S", lambda: self.save(True)),
                               ("导出图像 Ctrl+E", self.export), ("批量导出全部图像", self.export_all),
                               ("打开功能示例", self.demo)]: file.add_command(label=label, command=command)
        edit = tk.Menu(menu, tearoff=False); menu.add_cascade(label="编辑", menu=edit)
        for label, command in [("撤销 Ctrl+Z", self.undo), ("重做 Ctrl+Y / Ctrl+Shift+Z", self.redo),
                               ("隐藏 / 显示", self.toggle_visible), ("删除 Delete", self.remove)]: edit.add_command(label=label, command=command)
        align = tk.Menu(edit, tearoff=False); edit.add_cascade(label="对齐多个选中元素", menu=align)
        for mode, label in [("left", "左对齐"), ("right", "右对齐"), ("top", "顶部对齐"), ("bottom", "底部对齐"),
                            ("center_x", "水平中心对齐"), ("center_y", "垂直中心对齐")]:
            align.add_command(label=label, command=lambda m=mode: self.align(m))
        helpmenu = tk.Menu(menu, tearoff=False); menu.add_cascade(label="帮助", menu=helpmenu)
        helpmenu.add_command(label="快捷键与导入说明", command=self.help)
        helpmenu.add_command(label="打开使用说明", command=lambda: os.startfile(str(BASE / "README.md")) if (BASE / "README.md").exists() else self.help())
        self.root.configure(menu=menu)

    def bind_keys(self):
        for sequence, callback in [("<Control-o>", self.open_file), ("<Control-n>", self.new), ("<Control-s>", self.save),
                                   ("<Control-Shift-S>", lambda: self.save(True)), ("<Control-e>", self.export),
                                   ("<Control-y>", self.redo), ("<Control-Shift-Z>", self.redo)]:
            self.root.bind(sequence, lambda e, c=callback: (c(), "break")[-1])
        self.root.bind("<Control-z>", self.undo_key)
        self.root.bind("<Delete>", lambda e: self.remove() if not self.typing(e) else None)
        for key, dx, dy in [("Left", -1, 0), ("Right", 1, 0), ("Up", 0, 1), ("Down", 0, -1)]:
            self.root.bind("<" + key + ">", lambda e, x=dx, y=dy: self.nudge(e, x, y))
        self.root.bind("<Escape>", lambda e: self.cancel_drag())
        self.root.bind_all("<MouseWheel>", self.inspector_wheel, add="+")

    def inspector_wheel(self, event):
        if str(event.widget).startswith(str(self.property_host)):
            self.inspector.yview_scroll(-int(event.delta / 120), "units")
            return "break"

    @staticmethod
    def typing(event): return isinstance(event.widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox))

    def undo_key(self, event):
        if isinstance(event.widget, tk.Text):
            try: event.widget.edit_undo(); return "break"
            except tk.TclError: pass
        self.undo(); return "break"

    def refresh_all(self):
        self.doc.normalize()
        self.figmenu.configure(values=self.doc.names)
        if self.doc.names: self.figmenu.current(self.doc.active)
        self.draw()
        self.refresh_tree()
        self.build_properties()
        name = self.doc.path.name if self.doc.path else "未保存项目"
        self.root.title(f"{'* ' if self.doc.dirty else ''}{name} · 科研图像编辑器 {VERSION}")

    def queue_draw(self, event=None):
        if self.check: return
        if self.pending: self.root.after_cancel(self.pending)
        self.pending = self.root.after(160, self.draw)

    def draw(self):
        self.pending = None
        if not self.doc.figure: return
        if self.figure_widget: self.figure_widget.destroy()
        self.doc.normalize()
        fig = self.doc.figure
        w, h = fig._sfs_size_inches
        available_w, available_h = max(440, self.viewport.winfo_width() - 44), max(330, self.viewport.winfo_height() - 44)
        dpi = min(available_w / w, available_h / h) if self.zoom == "fit" else 100 * self.zoom
        fig.set_dpi(max(30, min(500, dpi)))
        self.canvas = StableCanvas(fig, self.host)
        self.figure_widget = self.canvas.get_tk_widget(); self.figure_widget.pack()
        self.canvas.draw()
        fw, fh = fig.bbox.width, fig.bbox.height
        self.viewport.coords(self.hostwindow, max(20, (self.viewport.winfo_width() - fw) / 2), max(20, (self.viewport.winfo_height() - fh) / 2))
        self.viewport.configure(scrollregion=(0, 0, max(fw + 40, self.viewport.winfo_width()), max(fh + 40, self.viewport.winfo_height())))
        for event, callback in [("button_press_event", self.press), ("motion_notify_event", self.motion),
                                ("button_release_event", self.release), ("draw_event", lambda e: self.overlay()),
                                ("scroll_event", self.wheel)]: self.canvas.mpl_connect(event, callback)
        self.overlay()

    def refresh_tree(self):
        if not hasattr(self, "tree") or not self.doc.figure: return
        self.tree_lock = True
        open_keys = {key for key in self.tree.get_children("") if self.tree.item(key, "open")}
        def opened(parent):
            for key in self.tree.get_children(parent):
                if self.tree.item(key, "open"): open_keys.add(key)
                opened(key)
        opened("")
        self.tree.delete(*self.tree.get_children(""))
        self.nodes = self.doc.nodes(); index = {node.key: node for node in self.nodes}
        search = self.search.get().casefold().strip()
        keep = set()
        for node in self.nodes:
            visible = node.artist is None or node.artist.get_visible()
            if (not self.only_visible.get() or visible) and (not search or search in node.title.casefold()):
                key = node.key
                while key and key not in keep:
                    keep.add(key); key = index[key].parent
        for node in self.nodes:
            if node.key not in keep: continue
            self.tree.insert(node.parent if node.parent in keep else "", "end", iid=node.key, text=node.title,
                             open=node.key in open_keys or isinstance(node.artist, (Figure, Axes, Legend)) or bool(search))
        selected = [key for key in self.doc.selected if self.tree.exists(key)]
        self.tree.selection_set(selected)
        self.tree_lock = False

    def tree_select(self, event=None):
        if self.tree_lock: return
        self.doc.selected = list(self.tree.selection())
        self.build_properties(); self.overlay()

    def choose(self, keys):
        self.doc.selected = keys
        self.tree_lock = True
        visible_keys = [key for key in keys if self.tree.exists(key)]
        self.tree.selection_set(visible_keys)
        for key in visible_keys: self.tree.see(key)
        self.tree_lock = False
        self.build_properties(); self.overlay()

    def build_properties(self):
        for widget in self.property_host.winfo_children(): widget.destroy()
        self.fields = []
        artists = [self.doc.lookup(key) for key in self.doc.selected]
        artists = [a for a in artists if a is not None]
        if not artists: self.selection_label.set("在图中点击，或从左侧选择元素"); return
        self.selection_label.set(f"选中 {len(artists)} 个元素：" + type(artists[0]).__name__)
        specs = properties(artists[0], self.doc.figure)
        if len(artists) > 1:
            available = [set(p[0] for p in properties(a, self.doc.figure)) for a in artists[1:]]
            specs = [p for p in specs if all(p[0] in keys for keys in available)]
        for row, (key, label, kind, value) in enumerate(specs):
            frame = ttk.Frame(self.property_host, padding=(7, 4)); frame.pack(fill="x")
            ttk.Label(frame, text=label).pack(anchor="w")
            if kind in ("text", "lines"):
                control = tk.Text(frame, height=3 if kind == "lines" else 2, wrap="word", undo=True, font=("Microsoft YaHei", 10))
                control.insert("1.0", str(value)); control.pack(fill="x")
                getter = lambda widget=control: widget.get("1.0", "end-1c")
            elif kind == "bool":
                var = tk.BooleanVar(value=value)
                ttk.Checkbutton(frame, variable=var).pack(anchor="w")
                getter = var.get
            else:
                display = f"{value:.6g}" if kind == "float" and value is not None else str(value)
                var = tk.StringVar(value=display)
                if kind.startswith("choice:"):
                    control = ttk.Combobox(frame, textvariable=var, values=kind.split(":", 1)[1].split(","))
                else: control = ttk.Entry(frame, textvariable=var)
                control.pack(side="left", fill="x", expand=True)
                if kind == "color":
                    ttk.Button(frame, text="选色", width=5, command=lambda v=var: self.pick_color(v)).pack(side="left", padx=4)
                getter = var.get
            self.fields.append((key, kind, getter, copy.deepcopy(value)))
        self.inspector.yview_moveto(0)

    def pick_color(self, var):
        try: color = colorchooser.askcolor(color=var.get()[:7], parent=self.root)[1]
        except tk.TclError: color = colorchooser.askcolor(parent=self.root)[1]
        if color: var.set(color)

    def apply(self):
        try:
            values = {}
            for key, kind, getter, original in self.fields:
                value = getter()
                if kind == "float": value = float(value)
                elif kind == "int": value = int(value)
                if kind == "float": changed = original is None or not math.isclose(value, float(original), rel_tol=1e-5, abs_tol=1e-6)
                else: changed = value != original
                if changed: values[key] = value
            if not values: self.status.set("属性没有变化。"); return
            keys = list(self.doc.selected)
            def action():
                for key in keys:
                    artist = self.doc.lookup(key)
                    if artist: apply_properties(artist, self.doc.figure, values)
            self.doc.change(action); self.refresh_all()
            self.status.set("属性已应用；Ctrl+Z 可撤销，Ctrl+Y 可重做。")
        except Exception as error: self.error("无法应用属性", error)

    def overlay(self):
        if not self.canvas: return
        widget = self.canvas._tkcanvas
        widget.delete("selection_overlay")
        renderer = self.doc.figure.canvas.get_renderer()
        height = self.doc.figure.bbox.height
        for key in self.doc.selected:
            artist = self.doc.lookup(key)
            if artist is None or not artist.get_visible(): continue
            try:
                box = artist_bounds(artist, self.doc.figure)
                if not np.isfinite(box.extents).all(): continue
                widget.create_rectangle(box.x0 - 3, height - box.y1 - 3, box.x1 + 3, height - box.y0 + 3,
                                        outline="#2674D9", width=1, dash=(4, 2), tags="selection_overlay")
            except Exception: pass
        widget.tag_raise("selection_overlay")

    def hit(self, event):
        candidates = []
        for node in self.nodes:
            artist = node.artist
            if artist is None or not artist.get_visible() or isinstance(artist, Figure): continue
            if node.title.startswith(("刻度线", "对侧刻度", "网格线", "边框", "画布背景", "绘图区背景")): continue
            try:
                if isinstance(artist, Text) and not artist.get_text(): continue
                contains, _ = artist.contains(event)
                if contains:
                    box = artist_bounds(artist, self.doc.figure)
                    area = max(1, box.width * box.height)
                    priority = 100 if isinstance(artist, Text) else 80 if isinstance(artist, Legend) else 65 if isinstance(artist, Line2D) else 60 if isinstance(artist, Patch) else 55 if isinstance(artist, AxesImage) else 1 if isinstance(artist, Axes) else 70
                    candidates.append((priority, -area, node.key))
            except Exception: pass
        return max(candidates)[2] if candidates else None

    def press(self, event):
        if event.button != 1: return
        key = self.hit(event)
        if not key:
            self.choose([]); return
        ctrl = event.key and ("control" in event.key or "ctrl" in event.key)
        if ctrl:
            self.choose([k for k in self.doc.selected if k != key] if key in self.doc.selected else self.doc.selected + [key]); return
        if key not in self.doc.selected: self.choose([key])
        self.drag = {"before": self.doc.capture(), "last": (event.x, event.y), "changed": False,
                     "resize": bool(event.key and "shift" in event.key)}
        self.figure_widget.focus_set()

    def motion(self, event):
        if not self.drag or event.x is None or event.y is None: return
        dx, dy = event.x - self.drag["last"][0], event.y - self.drag["last"][1]
        if abs(dx) + abs(dy) < 1: return
        fig = self.doc.figure
        for key in list(self.doc.selected):
            artist = self.doc.lookup(key)
            if artist is None: continue
            if self.drag["resize"] and isinstance(artist, Axes):
                x, y, w, h = artist.get_position().bounds
                artist.set_position([x, y, max(.03, w + dx / fig.bbox.width), max(.03, h + dy / fig.bbox.height)])
            elif self.drag["resize"] and isinstance(artist, Text):
                artist.set_fontsize(max(1, artist.get_fontsize() + dy * 72 / fig.dpi))
            elif self.drag["resize"] and isinstance(artist, Rectangle):
                transform = artist.get_data_transform()
                a, b = transform.inverted().transform([[0, 0], [dx, dy]])
                artist.set_width(max(.00001, artist.get_width() + b[0] - a[0]))
                artist.set_height(max(.00001, artist.get_height() + b[1] - a[1]))
            else: move_artist(artist, fig, dx, dy)
        self.drag["last"] = (event.x, event.y); self.drag["changed"] = True
        self.canvas.draw_idle()

    def release(self, event):
        if not self.drag: return
        if self.drag["changed"]: self.doc.remember(self.drag["before"])
        self.drag = None; self.refresh_all()
        self.status.set("位置 / 比例已调整；方向键微调 0.2 mm，Shift+方向键微调 1 mm。")

    def cancel_drag(self):
        if self.drag:
            self.doc.restore(self.drag["before"]); self.drag = None; self.refresh_all()

    def nudge(self, event, dx, dy):
        if self.typing(event) or not self.doc.selected: return
        distance = 1.0 if event.state & 1 else .2
        fig = self.doc.figure; px = distance / 25.4 * fig.dpi
        self.doc.change(lambda: [move_artist(self.doc.lookup(key), fig, dx * px, dy * px) for key in self.doc.selected if self.doc.lookup(key)])
        self.refresh_all(); return "break"

    def align(self, mode):
        artists = [self.doc.lookup(key) for key in self.doc.selected]
        artists = [a for a in artists if a is not None and not isinstance(a, Figure)]
        if len(artists) < 2: self.status.set("请先多选至少两个元素。"); return
        fig = self.doc.figure; renderer = fig.canvas.get_renderer()
        boxes = [artist_bounds(a, fig) for a in artists]
        def coord(box):
            return {"left": box.x0, "right": box.x1, "top": box.y1, "bottom": box.y0,
                    "center_x": (box.x0 + box.x1) / 2, "center_y": (box.y0 + box.y1) / 2}[mode]
        anchor = coord(boxes[0])
        self.doc.change(lambda: [move_artist(a, fig, anchor - coord(b) if mode in ("left", "right", "center_x") else 0,
                                            anchor - coord(b) if mode in ("top", "bottom", "center_y") else 0) for a, b in zip(artists[1:], boxes[1:])])
        self.refresh_all()

    def toggle_visible(self):
        artists = [self.doc.lookup(key) for key in self.doc.selected]
        if not artists: return
        self.doc.change(lambda: [a.set_visible(not a.get_visible()) for a in artists if a and not isinstance(a, Figure)])
        self.only_visible.set(False); self.refresh_all()

    def remove(self):
        artists = [self.doc.lookup(key) for key in self.doc.selected]
        if not artists: return
        def action():
            for a in artists:
                if a is None or isinstance(a, Figure): continue
                try: a.remove()
                except (NotImplementedError, ValueError): a.set_visible(False)
            self.doc.selected = []
        self.doc.change(action); self.refresh_all()

    def active_axes(self):
        for key in self.doc.selected:
            artist = self.doc.lookup(key)
            if isinstance(artist, Axes): return artist
            if artist is not None and artist.axes is not None: return artist.axes
        return self.doc.figure.axes[0] if self.doc.figure.axes else self.doc.figure.add_axes([.15, .15, .8, .7])

    def add_text(self):
        text = simpledialog.askstring("添加文字", "输入标题或注释文字：", initialvalue="New text", parent=self.root)
        if text is None: return
        def action():
            artist = self.doc.figure.text(.5, .9, text, fontsize=9, ha="center")
            self.doc.selected = [identity(artist)]
        self.doc.change(action); self.refresh_all()

    def add_legend(self):
        ax = self.active_axes()
        def action():
            handles, labels = ax.get_legend_handles_labels()
            if not handles: raise ValueError("绘图区中没有带系列名称的数据。可在系列属性中设置名称，再添加图例。")
            legend = ax.legend(handles, labels, title="Legend", fontsize=7, title_fontsize=8)
            self.doc.selected = [identity(legend)]
        try: self.doc.change(action); self.refresh_all()
        except Exception as error: self.error("无法添加图例", error)

    def add_arrow(self):
        def action():
            artist = self.active_axes().annotate("Note", (.65, .55), xytext=(.35, .75),
                       xycoords="axes fraction", textcoords="axes fraction", fontsize=8, arrowprops={"arrowstyle": "->"})
            self.doc.selected = [identity(artist)]
        self.doc.change(action); self.refresh_all()

    def add_rectangle(self):
        def action():
            artist = Rectangle((.35, .35), .2, .2, transform=self.doc.figure.transFigure, facecolor="none", edgecolor="#303030", lw=.8)
            self.doc.figure.add_artist(artist); self.doc.selected = [identity(artist)]
        self.doc.change(action); self.refresh_all()

    def undo(self):
        if self.drag: self.cancel_drag(); return
        if self.doc.undo(): self.refresh_all(); self.status.set("已撤销上一步操作。")
        else: self.status.set("没有可撤销的操作。")

    def redo(self):
        if self.doc.redo(): self.refresh_all(); self.status.set("已重做操作。")
        else: self.status.set("没有可重做的操作。")

    def switch_figure(self, event=None):
        self.doc.active = self.figmenu.current(); self.doc.selected = []; self.zoom = "fit"; self.refresh_all()

    def fit(self): self.zoom = "fit"; self.draw()
    def scale(self, factor):
        current = self.doc.figure.dpi / 100 if self.zoom == "fit" else self.zoom
        self.zoom = min(5, max(.3, current * factor)); self.draw()
    def wheel(self, event):
        if event.key and ("ctrl" in event.key or "control" in event.key): self.scale(1.15 if event.button == "up" else 1 / 1.15)

    def confirm_changed(self):
        if not self.doc.dirty: return True
        result = messagebox.askyesnocancel("保存项目", "当前项目有未保存的修改。是否保存？", parent=self.root)
        if result is None: return False
        if result: return self.save()
        return True

    def new(self):
        if self.confirm_changed(): self.doc = blank_document(); self.zoom = "fit"; self.refresh_all()
    def demo(self):
        if self.confirm_changed(): self.doc = demo_document(); self.zoom = "fit"; self.refresh_all()

    def open_file(self, path=None):
        if not self.confirm_changed(): return
        if not path:
            path = filedialog.askopenfilename(parent=self.root, title="导入绘图源文件、数据或项目",
                filetypes=[("科研图 / 数据 / 源代码", "*.sfig *.py *.xlsx *.csv *.tsv *.png *.jpg *.jpeg *.tif *.tiff"),
                           ("科研图项目", "*.sfig"), ("Python Matplotlib 源文件", "*.py"),
                           ("数据表格", "*.xlsx *.csv *.tsv"), ("位图", "*.png *.jpg *.jpeg *.tif *.tiff"), ("所有文件", "*.*")])
        if not path: return
        self.status.set("正在读取源文件并构建可编辑图像……"); self.root.update_idletasks()
        try:
            suffix = Path(path).suffix.lower()
            if suffix == ".sfig": doc = Document.open(path)
            elif suffix == ".py": doc = load_python(path)
            elif suffix in (".csv", ".tsv", ".xlsx"):
                dialog = DataDialog(self.root, path); doc = dialog.result
                if doc is None: return
            elif suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff"): doc = load_image(path)
            else: raise ValueError("支持 .py / .xlsx / .csv / .tsv / .sfig，以及作为底图导入的常见位图。")
            for old in self.doc.figures:
                import matplotlib.pyplot as plt
                plt.close(old)
            self.doc = doc; self.zoom = "fit"; self.refresh_all()
            self.status.set(f"已导入 {len(doc.figures)} 张图。点击元素可编辑；位图内的已有文字和线条仍是像素。")
        except Exception as error: self.error("导入失败", error)

    def save(self, save_as=False):
        path = None if save_as else self.doc.path
        if not path:
            path = filedialog.asksaveasfilename(parent=self.root, title="保存可继续编辑的项目", defaultextension=".sfig", filetypes=[("科研图项目", "*.sfig")])
        if not path: return False
        try:
            self.doc.save(path); self.refresh_all(); self.status.set("项目已保存，包含全部图像及当前编辑结果。"); return True
        except Exception as error: self.error("保存失败", error); return False

    def export(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="导出当前图像", defaultextension=".svg",
            filetypes=[("可编辑 SVG", "*.svg"), ("矢量 PDF", "*.pdf"), ("PNG", "*.png"), ("TIFF", "*.tiff")])
        if not path: return
        try:
            dpi = getattr(self.doc.figure, "_sfs_export_dpi", 600)
            self.doc.export(path); self.draw()
            self.status.set(f"已导出。物理尺寸按画布设置保留，SVG 文字可编辑，位图为 {dpi} dpi。")
        except Exception as error: self.error("导出失败", error)

    def export_all(self):
        folder = filedialog.askdirectory(parent=self.root, title="选择全部图像的导出目录")
        if not folder: return
        active = self.doc.active
        try:
            for index, figure in enumerate(self.doc.figures):
                self.doc.active = index
                for extension in ("svg", "pdf", "png"):
                    self.doc.export(Path(folder) / f"figure_{index + 1}.{extension}")
            self.status.set(f"已批量导出 {len(self.doc.figures)} 张图的 SVG、PDF 和 PNG。")
        except Exception as error: self.error("批量导出未完成", error)
        finally:
            self.doc.active = active; self.draw()

    def help(self):
        messagebox.showinfo("使用帮助", "导入 .py 绘图源代码、Excel/CSV/TSV 数据或 .sfig 项目。\n"
            "Python 导入会运行脚本；内置 Matplotlib、NumPy 和 openpyxl，未包含其他第三方包。\n\n"
            "点击图中元素或从左侧元素树选择。Ctrl 多选；拖动移动；Shift 拖动绘图区改比例、拖动文字改字号。\n"
            "方向键微调 0.2 mm，Shift+方向键微调 1 mm。\n"
            "Ctrl+Z 撤销，Ctrl+Y / Ctrl+Shift+Z 重做，Delete 移除，Esc 取消拖动。\n"
            "Ctrl+O 导入，Ctrl+S 保存项目，Ctrl+E 导出。\n\n"
            "可编辑 Matplotlib 元素包括标题、图例标题和项目、坐标轴、刻度、图形、注释和色条。\n"
            "PNG/JPG 导入为底图，其中原有的文字和线条无法作为独立对象编辑。", parent=self.root)

    def error(self, title, error):
        logging.exception(title)
        self.refresh_all()
        messagebox.showerror(title, str(error), parent=self.root)
        self.status.set(title + "；原始文件保留，当前项目仍可操作。")

    def quit(self):
        if self.confirm_changed(): self.root.destroy()


def main():
    configure_display()
    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?")
    parser.add_argument("--self-test", type=Path)
    args = parser.parse_args()
    if args.self_test:
        from selftest import run
        run(args.self_test)
        return
    log_dir = Path(os.environ.get("LOCALAPPDATA", BASE)) / "ScientificFigureStudio"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_dir / "error.log", level=logging.ERROR, encoding="utf-8")
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names(): style.theme_use("vista")
    app = App(root)
    if args.file: root.after(200, lambda: app.open_file(args.file))
    root.mainloop()


if __name__ == "__main__": main()
