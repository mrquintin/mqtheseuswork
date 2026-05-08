#!/usr/bin/env python3
"""Launch the Dialectic live-analysis dashboard (wrapper for ``python -m dialectic``)."""

import argparse
import multiprocessing
import os
import sys
import traceback
from pathlib import Path


def _crash_log_path() -> Path:
    """User-visible path for startup crashes — same dir as session recordings."""
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "Dialectic"
    elif sys.platform == "win32":
        import os as _os
        d = Path(_os.environ.get("APPDATA", str(Path.home()))) / "Dialectic"
    else:
        d = Path.home() / ".dialectic"
    d.mkdir(parents=True, exist_ok=True)
    return d / "crash.log"


def _write_crash_log(exc: BaseException) -> Path:
    """Dump a full traceback somewhere the user can actually find it.

    Packaged .app bundles have no attached console, so an unhandled
    exception at startup leaves no visible trace. This writes one.
    """
    path = _crash_log_path()
    try:
        with path.open("a", encoding="utf-8") as f:
            import datetime
            f.write("\n" + "=" * 72 + "\n")
            f.write(f"Dialectic crash at {datetime.datetime.now().isoformat()}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Platform: {sys.platform}\n")
            f.write(f"Frozen: {bool(getattr(sys, 'frozen', False))}\n")
            f.write("-" * 72 + "\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
    except Exception:
        # Last-resort: don't let the crash-logger itself crash the process.
        pass
    return path


def _prime_speaker_profiles() -> None:
    """Initialise the per-speaker methodology profile store before the UI starts.

    Profiles live on the local machine only. We pre-create the directory so a
    first-time launch doesn't fail when the dashboard tries to load profiles
    for the active speakers. The path can be overridden by setting the
    ``DIALECTIC_SPEAKER_PROFILES_DIR`` env var (consumed downstream by
    code that constructs a :class:`SpeakerProfileStore`).
    """
    try:
        from noosphere.voices.profile_store import (
            SpeakerProfileStore,
            default_profile_dir,
        )
    except Exception:
        # Noosphere unavailable in this build — skip silently. The dashboard's
        # methodology mirror will degrade to "no baseline" for every speaker.
        return
    override = os.environ.get("DIALECTIC_SPEAKER_PROFILES_DIR")
    root = Path(override) if override else default_profile_dir()
    try:
        SpeakerProfileStore(root)
    except Exception:
        pass


def _peel_known_args() -> None:
    """Strip our own flags from sys.argv before delegating to ``dialectic.__main__``.

    We add ``--speaker-profiles-dir`` here so users can point at a custom
    profile directory without forking the dashboard's own argparser.

    The argument-map flags are also peeled here. They translate into env
    vars consumed by ``dialectic.argument_map_builder.BuilderConfig.load``
    and the dashboard wiring — that way the dashboard's own argparser
    doesn't need to know about them and they survive the
    ``python -m dialectic`` indirection.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--speaker-profiles-dir", default=None)
    parser.add_argument(
        "--argument-map-config",
        default=None,
        help="Path to a TOML file overriding ArgumentMapBuilder thresholds.",
    )
    parser.add_argument(
        "--argument-map-export-dir",
        default=None,
        help=(
            "Directory to write end-of-session argument-map exports "
            "(JSON, SVG, Markdown) into. Defaults to the per-session "
            "recording directory."
        ),
    )
    parser.add_argument(
        "--argument-map-sync-codex",
        action="store_true",
        help=(
            "Opt in to syncing the argument map to the Codex at session end. "
            "Off by default — the map is local-only unless explicitly enabled."
        ),
    )
    known, rest = parser.parse_known_args()
    if known.speaker_profiles_dir:
        os.environ["DIALECTIC_SPEAKER_PROFILES_DIR"] = known.speaker_profiles_dir
    if known.argument_map_config:
        os.environ["DIALECTIC_ARGUMENT_MAP_CONFIG"] = known.argument_map_config
    if known.argument_map_export_dir:
        os.environ["DIALECTIC_ARGUMENT_MAP_EXPORT_DIR"] = known.argument_map_export_dir
    # Privacy default: opt-in only. Saving locally always works.
    os.environ["DIALECTIC_ARGUMENT_MAP_SYNC_CODEX"] = (
        "1" if known.argument_map_sync_codex else "0"
    )
    # Replace argv with the leftovers so __main__'s parser sees only its args.
    sys.argv = [sys.argv[0]] + rest


def _main() -> None:
    _peel_known_args()
    _prime_speaker_profiles()
    # Deferred import so ImportError inside the package is captured by our
    # try/except (instead of dying at module import time with no log).
    from dialectic.__main__ import main
    main()


if __name__ == "__main__":
    # `multiprocessing.freeze_support()` must live *inside* the __name__ guard
    # so it only fires in the main process. When placed at module scope it
    # runs on every re-import (including from PyInstaller's bootloader and
    # from any worker process that happens to import run.py), which can
    # surface confusing secondary errors.
    if getattr(sys, "frozen", False):
        multiprocessing.freeze_support()

    try:
        _main()
    except Exception as e:
        log_path = _write_crash_log(e)
        # Also print to stderr for users running from a terminal.
        print(
            f"\n[dialectic] Fatal startup error. See {log_path} for details.",
            file=sys.stderr,
        )
        traceback.print_exc()
        sys.exit(1)
