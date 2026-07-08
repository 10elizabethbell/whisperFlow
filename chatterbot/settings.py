"""Persisted user settings for the menu-bar toggles.

Stored as JSON at ~/.config/chatterbot/settings.json (next to the
personal dictionary) so the same settings apply whether the app is
launched from the terminal or the .app bundle. Unknown keys are
dropped and missing keys fall back to DEFAULTS, so stale files from
older versions never break startup.
"""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH = Path.home() / ".config" / "chatterbot" / "settings.json"

DEFAULTS = {
    "type_at_cursor": True,  # inject the text at the cursor via keystrokes
    "copy_to_clipboard": False,  # also place the text on the pasteboard
}


def load() -> dict[str, bool]:
    settings = dict(DEFAULTS)
    try:
        stored = json.loads(SETTINGS_PATH.read_text())
        settings.update({k: bool(stored[k]) for k in DEFAULTS if k in stored})
    except (OSError, ValueError):
        pass
    return settings


def save(settings: dict[str, bool]) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")
    except OSError as e:
        print(f"  ⚠ could not save settings: {e!r}", flush=True)
