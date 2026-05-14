# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows DeskPilot executable."""

from pathlib import Path


ROOT = Path(SPECPATH).parent.parent

block_cipher = None

a = Analysis(
    [str(ROOT / "packaging" / "desktop_agent_entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "examples"), "examples"),
        (str(ROOT / "docs"), "docs"),
        (str(ROOT / "packaging" / "default-config.yaml"), "."),
        (str(ROOT / "README.md"), "."),
    ],
    hiddenimports=[
        "yaml",
        "mss",
        "mss.tools",
        "desktop_agent.platforms.windows.uia",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="deskpilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
