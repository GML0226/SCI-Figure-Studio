"""Behavioral checks, also executable inside the portable binary."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from xml.etree import ElementTree as ET

import numpy as np
from matplotlib.text import Annotation
from matplotlib.backends.backend_agg import FigureCanvasAgg

from core import Document, identity, properties, apply_properties, move_artist, position_mm
from importers import demo_document, create_chart, load_python, table_preview


def run(report_path):
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    results = []
    root = None
    try:
        doc = demo_document()
        fig = doc.figure
        title = fig.axes[0].title; key = identity(title)
        doc.change(lambda: apply_properties(title, fig, {"text": "Changed title", "font_size": 12}))
        assert doc.lookup(key).get_text() == "Changed title"
        assert doc.undo() and doc.lookup(key).get_text() == "Method comparison"
        assert doc.redo() and doc.lookup(key).get_fontsize() == 12
        results.append("undo/redo restores text, font size and artist identities")

        fig = doc.figure; legend = fig.axes[0].get_legend(); lk = identity(legend)
        doc.change(lambda: apply_properties(legend, fig, {"title": "Methods edited", "ncols": 2, "labels": "Control\nProposed"}))
        legend = doc.lookup(lk)
        assert legend.get_title().get_text() == "Methods edited" and legend._ncols == 2
        assert legend.get_texts()[1].get_text() == "Proposed"
        doc.undo(); assert doc.lookup(lk).get_title().get_text() == "Methods"
        results.append("legend title, entries and column layout are editable and reversible")

        fig = doc.figure; patch = fig.axes[0].patches[0]
        doc.change(lambda: apply_properties(patch, fig, {"facecolor": "#123456", "hatch": "//", "width": .25}))
        assert patch.get_hatch() == "//" and patch.get_width() == .25
        doc.undo(); results.append("bar geometry, color and hatch undo")

        fig = doc.figure; xlabel = fig.axes[1].xaxis.label
        old = position_mm(xlabel, fig).copy()
        move_artist(xlabel, fig, fig.dpi / 25.4 * 3, 0)
        FigureCanvasAgg(fig).draw()
        assert np.allclose(position_mm(xlabel, fig), old + [3, 0], atol=.01)
        fig.set_dpi(180); FigureCanvasAgg(fig).draw()
        assert np.allclose(position_mm(xlabel, fig), old + [3, 0], atol=.01)
        note = next(t for t in fig.axes[1].texts if isinstance(t, Annotation))
        move_artist(note, fig, 5, 3); FigureCanvasAgg(fig).draw()
        assert note.anncoords == "figure fraction"
        results.append("label and annotation drag positions survive DPI changes")

        scatter = fig.axes[1].collections[0]
        apply_properties(scatter, fig, {"size": 48, "facecolor": "#AA3311"})
        assert scatter.get_sizes()[0] == 48
        results.append("scatter size and style editing")

        tick = fig.axes[0].get_xticklabels()[0]
        apply_properties(tick, fig, {"text": "Revised A"})
        FigureCanvasAgg(fig).draw(); assert fig.axes[0].get_xticklabels()[0].get_text() == "Revised A"
        results.append("tick label text persists after redraw")

        project = report_path.parent / "test_roundtrip.sfig"
        doc.save(project); restored = Document.open(project)
        assert len(restored.nodes()) > 100 and restored.figure.axes[0].get_xticklabels()[0].get_text() == "Revised A"
        for ext in ("svg", "pdf", "png", "tiff"):
            restored.export(report_path.parent / f"test_export.{ext}", dpi=120)
        nodes = ET.parse(report_path.parent / "test_export.svg").findall(".//{http://www.w3.org/2000/svg}text")
        assert nodes and any("Revised A" in "".join(node.itertext()) for node in nodes)
        results.append("project round-trip and SVG/PDF/PNG/TIFF export with editable SVG text")

        table = [["Methods", "Set A", "Set B"], ["Random", .55, .56], ["Half", "NULL", .81], ["Full", .72, .82]]
        data = create_chart(table, 0, [1, 2], percent=True, series_rows=True)
        assert len(data.figure.axes[0].patches) == 5
        assert sorted(round(p.get_height(), 2) for p in data.figure.axes[0].patches) == [55, 56, 72, 81, 82]
        results.append("generic data import preserves missing values and converts proportions")

        source = report_path.parent / "source_example.py"
        source.write_text("import matplotlib.pyplot as plt\nfig, ax=plt.subplots()\nax.plot([0,1],[2,3], label='Trace')\nax.legend(title='Source legend')\nax.set_title('Imported source')\nplt.show()\n", encoding="utf-8")
        imported = load_python(source)
        assert len(imported.figures) == 1 and imported.figure.axes[0].get_title() == "Imported source"
        results.append("Python source capture without blocking show")

        from app import BASE
        example = BASE / "examples" / "comparison" / "plot_comparison.py"
        if example.exists():
            comparison = load_python(example)
            assert len(comparison.figures) == 3
            assert sum(len(ax.patches) for ax in comparison.figures[0].axes) == 24
            workbook = next(example.parent.glob("1.*.xlsx"))
            rows, sheets = table_preview(workbook)
            assert sheets and rows[1][1] == .5476
            imported_table = create_chart(rows, 0, [1,2], percent=True, series_rows=True)
            assert len(imported_table.figure.axes[0].patches) == 10
            results.append("original multi-figure source and Excel import without external runtime")

        bounded = demo_document()
        for index in range(45): bounded.change(lambda i=index: bounded.figure.axes[0].set_title(str(i)))
        assert len(bounded.past) == 40
        bounded.undo(); bounded.change(lambda: bounded.figure.axes[0].set_title("new branch"))
        assert not bounded.future
        results.append("bounded history and redo branch reset")

        from app import App, configure_display
        configure_display()
        root = tk.Tk(); root.withdraw()
        app = App(root, demo_document(), check=True); root.update_idletasks(); app.draw()
        first = app.doc.figure.axes[0].title; title_key = identity(first)
        app.choose([title_key])
        for key, kind, getter, original in app.fields:
            if key == "text":
                # Exercise the same Apply handler used by the property button.
                app.fields = [("text", "text", lambda: "GUI title edited", original)]
                break
        app.apply(); assert app.doc.lookup(title_key).get_text() == "GUI title edited"
        app.undo_key(SimpleNamespace(widget=app.root))
        assert app.doc.lookup(title_key).get_text() == "Method comparison"
        app.redo(); assert app.doc.lookup(title_key).get_text() == "GUI title edited"
        assert app.root.bind("<Control-z>") and app.root.bind("<Control-y>")
        ax = app.doc.figure.axes[0]; key = identity(ax)
        app.choose([key]); old = ax.get_position().bounds
        app.drag = {"before": app.doc.capture(), "last": (100,100), "changed": False, "resize": True}
        app.motion(SimpleNamespace(x=110,y=105)); app.release(None)
        assert app.doc.lookup(key).get_position().width > old[2]
        app.undo(); assert np.allclose(app.doc.lookup(key).get_position().bounds, old)
        results.append("native GUI, Apply, undo button/Ctrl+Z binding, redo and drag resize")
        root.destroy(); root = None

        report = {"passed": True, "checks": results, "check_count": len(results)}
    except Exception:
        import traceback
        report = {"passed": False, "checks": results, "error": traceback.format_exc()}
    finally:
        if root:
            try: root.destroy()
            except Exception: pass
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["passed"]: raise RuntimeError(report["error"])
    return report
