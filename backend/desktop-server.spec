from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


root = Path(SPECPATH).resolve()
hidden_imports = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + collect_submodules("sqlalchemy.dialects.sqlite")
    + collect_submodules("pydantic")
    + collect_submodules("celery")
)

a = Analysis(
    [str(root / "app" / "desktop_server.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "alembic.ini"), "."),
        (str(root / "migrations"), "migrations"),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JobFlow.Server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="JobFlow.Server",
)
