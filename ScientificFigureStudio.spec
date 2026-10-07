# Compact, single-file Windows build. No Qt, scipy, pandas or notebook runtime.
from pathlib import Path
root = Path(SPECPATH)
a = Analysis(
    [str(root / 'src' / 'app.py')],
    pathex=[str(root / 'src')],
    binaries=[],
    datas=[(str(root / 'assets' / 'app.ico'), '.')],
    hiddenimports=['matplotlib.backends.backend_tkagg', 'matplotlib.backends.backend_agg',
                   'matplotlib.backends.backend_pdf', 'matplotlib.backends.backend_svg', 'openpyxl'],
    hookspath=[], hooksconfig={'matplotlib': {'backends': ['TkAgg', 'Agg', 'pdf', 'svg']}},
    runtime_hooks=[], excludes=['PyQt5','PyQt6','PySide2','PySide6','scipy','pandas','IPython',
                               'jupyter','notebook','pytest','matplotlib.testing','numpy.testing'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='ScientificFigureStudio', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False,
          icon=str(root / 'assets' / 'app.ico'))
