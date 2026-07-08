"""Insert text into the frontmost app by synthesizing keyboard events.

The text is typed directly via CGEvent Unicode keystrokes, so it never
touches the pasteboard — nothing for clipboard managers to capture and
the user's clipboard is left untouched. Slightly slower than a paste on
very long text, but works in nearly every app (native, Electron, web).

Posting key events requires the hosting app to have Accessibility
permission; without it the events are silently dropped.
"""

from __future__ import annotations

import ctypes
import time

import Quartz

_carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")


def secure_input_active() -> bool:
    """True when a password field (or Terminal's Secure Keyboard Entry) holds
    secure event input — synthetic keystrokes are pointless and the text
    would land in a password box. Callers should skip inserting."""
    return bool(_carbon.IsSecureEventInputEnabled())


# CGEventKeyboardSetUnicodeString caps each event at 20 UTF-16 code units
CHUNK_UTF16_UNITS = 20

# pause between chunk events so slower apps (Electron, web views) don't
# drop or reorder keystrokes
INTER_CHUNK_DELAY = 0.005


def _post_unicode_chunk(chunk: str) -> None:
    utf16_len = len(chunk.encode("utf-16-le")) // 2
    for key_down in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(None, 0, key_down)
        # clear modifiers so a still-held hotkey doesn't turn the text
        # into shortcuts
        Quartz.CGEventSetFlags(event, 0)
        Quartz.CGEventKeyboardSetUnicodeString(event, utf16_len, chunk)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def insert_text(text: str) -> None:
    """Type `text` at the cursor of whatever app is focused."""
    if not text:
        return
    # chunk on UTF-16 units, keeping surrogate pairs (emoji etc.) intact
    units: list[str] = []
    count = 0
    for ch in text:
        ch_units = len(ch.encode("utf-16-le")) // 2
        if count + ch_units > CHUNK_UTF16_UNITS and units:
            _post_unicode_chunk("".join(units))
            time.sleep(INTER_CHUNK_DELAY)
            units, count = [], 0
        units.append(ch)
        count += ch_units
    if units:
        _post_unicode_chunk("".join(units))
