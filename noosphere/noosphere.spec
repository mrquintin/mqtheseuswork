# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Noosphere CLI.
#
# Build:
#     cd noosphere && pyinstaller noosphere.spec
#
# Notes:
#   * Single-directory bundle (not onefile) — torch + transformers are too large
#     to extract to a temp dir on every invocation.
#   * Sentence-transformers / transformers model weights are NOT bundled.
#     They are downloaded on first run to the platform HuggingFace cache
#     (~/.cache/huggingface by default). Bundling them would add 2GB+ and
#     prevents users from choosing different models.
#   * Alembic migrations and alembic.ini are bundled as data files so the
#     frozen binary can run DB upgrades at startup.
#   * Console mode is required — Noosphere is a CLI, not a GUI. On macOS we
#     intentionally do NOT emit a .app bundle.

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None


# --- Hidden imports --------------------------------------------------------
# PyInstaller's static analysis misses dynamic imports inside noosphere itself
# and many of its heavy ML dependencies. Collect submodules defensively.

hiddenimports = []
hiddenimports += collect_submodules("noosphere")
hiddenimports += collect_submodules("noosphere.coherence")
hiddenimports += collect_submodules("noosphere.methods")
hiddenimports += collect_submodules("noosphere.cascade")
hiddenimports += collect_submodules("noosphere.cli_commands")
hiddenimports += collect_submodules("noosphere.decay")
hiddenimports += collect_submodules("noosphere.docgen")
hiddenimports += collect_submodules("noosphere.evaluation")
hiddenimports += collect_submodules("noosphere.external_battery")
hiddenimports += collect_submodules("noosphere.inference")
hiddenimports += collect_submodules("noosphere.interop")
hiddenimports += collect_submodules("noosphere.ledger")
hiddenimports += collect_submodules("noosphere.mitigations")
hiddenimports += collect_submodules("noosphere.peer_review")
hiddenimports += collect_submodules("sentence_transformers")
hiddenimports += collect_submodules("transformers")
hiddenimports += collect_submodules("sklearn")
hiddenimports += collect_submodules("scipy")
hiddenimports += collect_submodules("spacy")

hiddenimports += [
    "typer",
    "rich",
    "click",
    "anthropic",
    "openai",
    "sqlmodel",
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "alembic",
    "alembic.runtime.migration",
    "alembic.script",
    "pydantic",
    "pydantic_settings",
    "structlog",
    "sentence_transformers",
    "torch",
    "numpy",
    "scipy",
    "sklearn",
    "spacy",
    "networkx",
    "hdbscan",
    "umap",
    "transformers",
    "pynacl",
    "zstandard",
    "yaml",
    "matplotlib",
]


# --- Data files ------------------------------------------------------------
# Bundle Alembic migration scripts and configuration so frozen binary can
# run migrations against the user's data directory.

datas = [
    ("alembic", "alembic"),
    ("alembic.ini", "."),
]

# Pull in package-level data files that libraries advertise via entry points.
datas += collect_data_files("sentence_transformers", include_py_files=False)
datas += collect_data_files("transformers", include_py_files=False)
datas += collect_data_files("spacy", include_py_files=False)


# --- Exclusions ------------------------------------------------------------
# Trim obvious dead weight. Keep core matplotlib (some adapters plot), but
# drop interactive GUI backends.

excludes = [
    "tensorflow",
    "tensorboard",
    "jupyter",
    "IPython",
    "pytest",
    "matplotlib.backends",
]


a = Analysis(
    ["noosphere/__main__.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["scripts/build_hooks/hook-noosphere.py"],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="noosphere",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="noosphere",
)
