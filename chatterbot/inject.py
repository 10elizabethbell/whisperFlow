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
# The AX* symbols live in HIServices, re-exported by the ApplicationServices
# umbrella. The matching PyObjC framework isn't a dependency, so bind via
# ctypes instead.
_appservices = ctypes.CDLL(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_appservices.AXIsProcessTrusted.restype = ctypes.c_bool
_cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")


def accessibility_trusted() -> bool:
    """True when this process may post keyboard events. Without the
    Accessibility permission, macOS drops synthetic keystrokes silently
    (no error, no exception) — so this must be checked to explain why
    typing 'does nothing'. The grant attaches to the running binary
    (the terminal, or ChatterBot.app when launched as a bundle), so a
    grant on one host does not cover the other."""
    return bool(_appservices.AXIsProcessTrusted())


def prompt_for_accessibility() -> bool:
    """Like accessibility_trusted(), but when untrusted asks macOS to show
    its 'grant Accessibility' dialog, which also adds this app to the
    Settings list so the user only has to flip the switch. Returns the
    current trust state (still False right after prompting — the grant
    takes effect on the next launch). Falls back to the plain check if
    the CoreFoundation glue can't be built."""
    try:
        vp = ctypes.c_void_p
        prompt_key = vp.in_dll(_appservices, "kAXTrustedCheckOptionPrompt")
        cf_true = vp.in_dll(_cf, "kCFBooleanTrue")
        # the CallBacks symbols are structs — pass their address, not value
        key_cb = ctypes.addressof(vp.in_dll(_cf, "kCFTypeDictionaryKeyCallBacks"))
        val_cb = ctypes.addressof(vp.in_dll(_cf, "kCFTypeDictionaryValueCallBacks"))

        keys = (vp * 1)(prompt_key.value)
        vals = (vp * 1)(cf_true.value)
        _cf.CFDictionaryCreate.restype = vp
        _cf.CFDictionaryCreate.argtypes = [vp, vp, vp, ctypes.c_long, vp, vp]
        options = _cf.CFDictionaryCreate(
            None, ctypes.addressof(keys), ctypes.addressof(vals), 1, key_cb, val_cb
        )

        _appservices.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        _appservices.AXIsProcessTrustedWithOptions.argtypes = [vp]
        trusted = bool(_appservices.AXIsProcessTrustedWithOptions(options))
        _cf.CFRelease.argtypes = [vp]
        _cf.CFRelease(options)
        return trusted
    except (ValueError, OSError):
        return accessibility_trusted()


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
