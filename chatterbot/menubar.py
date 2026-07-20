"""Menu-bar app: click the mic icon to dictate.

Left-click toggles recording. While recording, a timer polls the
recorder's VAD state and auto-stops once you've spoken and then gone
quiet for AUTO_STOP_SILENCE seconds. Right-click shows a menu with two
output toggles (Type at Cursor, Copy to Clipboard — persisted via
settings.py) and Quit.

Icon: the chatterbot logo (circle + wave, see icons.py) — faint while
the model loads, outlined when idle, filled while recording, dimmed-filled
while transcribing/cleaning.

Transcription + cleanup + paste run on a worker thread so the menu bar
never blocks on the Haiku call; icon updates hop back to the main thread.
"""

from __future__ import annotations

import threading

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSControlStateValueOff,
    NSControlStateValueOn,
    NSEventMaskLeftMouseUp,
    NSEventMaskRightMouseUp,
    NSEventTypeRightMouseUp,
    NSMenu,
    NSMenuItem,
    NSPasteboard,
    NSPasteboardTypeString,
    NSStatusBar,
    NSVariableStatusItemLength,
)
import objc
from Foundation import NSObject, NSTimer

from chatterbot import settings

AUTO_STOP_SILENCE = 2.0  # stop this many seconds after the speaker goes quiet
NO_SPEECH_TIMEOUT = 10.0  # cancel if nothing was said at all
MAX_UTTERANCE = 120.0  # hard cap

LOADING, IDLE, RECORDING, PROCESSING = "loading", "idle", "recording", "processing"
STATES = (LOADING, IDLE, RECORDING, PROCESSING)


class ChatterBotApp(NSObject):
    def initWithUseLLM_(self, use_llm: bool):
        self = objc.super(ChatterBotApp, self).init()
        if self is None:
            return None
        self._use_llm = use_llm
        self._settings = settings.load()
        self._state = LOADING
        self._recorder = None
        self._transcriber = None
        self._cleaner = None
        return self

    # --- lifecycle ---

    def applicationDidFinishLaunching_(self, _notification) -> None:
        from chatterbot.icons import logo

        self._icons = {state: logo(state) for state in STATES}
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        button = self._status_item.button()
        button.setTarget_(self)
        button.setAction_("clicked:")
        button.sendActionOn_(NSEventMaskLeftMouseUp | NSEventMaskRightMouseUp)
        self._apply_icon()

        self._menu = NSMenu.alloc().init()
        self._type_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Type at Cursor", "toggleTypeAtCursor:", ""
        )
        self._type_item.setTarget_(self)
        self._menu.addItem_(self._type_item)
        self._copy_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Copy to Clipboard", "toggleCopyToClipboard:", ""
        )
        self._copy_item.setTarget_(self)
        self._menu.addItem_(self._copy_item)
        self._menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit chatterbot", "terminate:", "q"
        )
        self._menu.addItem_(quit_item)
        self._apply_menu_states()

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.1, self, "tick:", None, True
        )
        threading.Thread(target=self._load_models, daemon=True).start()

    @objc.python_method
    def _load_models(self) -> None:
        from chatterbot.audio import Recorder
        from chatterbot.transcriber import Transcriber

        transcriber = Transcriber()
        transcriber.warm_up()
        recorder = Recorder()
        cleaner = None
        if self._use_llm:
            from chatterbot.cleanup import Cleaner

            cleaner = Cleaner()
            cleaner.warm_up()
        self._transcriber, self._recorder, self._cleaner = transcriber, recorder, cleaner
        self._set_state(IDLE)
        print("[app] ready — click the mic in the menu bar", flush=True)

        if self._settings["type_at_cursor"]:
            from chatterbot.inject import prompt_for_accessibility

            # Without Accessibility, macOS drops synthetic keystrokes with no
            # error — the app would look like it does nothing. Surface it now
            # and trigger the system grant dialog (which also adds this app to
            # the Settings list). The grant takes effect on next launch.
            if not prompt_for_accessibility():
                print(
                    "  ⚠ Accessibility permission missing — typing at the cursor "
                    "will be silently dropped.\n"
                    "    Grant it in the dialog (or System Settings → Privacy & "
                    "Security → Accessibility), then relaunch.\n"
                    "    Note: the grant is per-app — if you granted your terminal "
                    "before, ChatterBot.app still needs its own.",
                    flush=True,
                )

    # --- UI events (main thread) ---

    def clicked_(self, _sender) -> None:
        event = NSApplication.sharedApplication().currentEvent()
        if event is not None and event.type() == NSEventTypeRightMouseUp:
            self._status_item.popUpStatusItemMenu_(self._menu)
            return
        if self._state == IDLE:
            self._recorder.open()
            self._recorder.start()
            self._set_state(RECORDING)
            print("● recording ... (auto-stops on silence, or click again)", flush=True)
        elif self._state == RECORDING:
            self._finish_recording("clicked")
        # LOADING / PROCESSING: ignore clicks

    def toggleTypeAtCursor_(self, _sender) -> None:
        self._toggle("type_at_cursor")

    def toggleCopyToClipboard_(self, _sender) -> None:
        self._toggle("copy_to_clipboard")

    @objc.python_method
    def _toggle(self, key: str) -> None:
        self._settings[key] = not self._settings[key]
        settings.save(self._settings)
        self._apply_menu_states()
        if not (self._settings["type_at_cursor"] or self._settings["copy_to_clipboard"]):
            print("  ⚠ both outputs are off — dictation will go nowhere", flush=True)

    @objc.python_method
    def _apply_menu_states(self) -> None:
        self._type_item.setState_(
            NSControlStateValueOn
            if self._settings["type_at_cursor"]
            else NSControlStateValueOff
        )
        self._copy_item.setState_(
            NSControlStateValueOn
            if self._settings["copy_to_clipboard"]
            else NSControlStateValueOff
        )

    def tick_(self, _timer) -> None:
        if self._state != RECORDING:
            return
        r = self._recorder
        if r.has_speech and r.silence_seconds >= AUTO_STOP_SILENCE:
            self._finish_recording("silence")
        elif not r.has_speech and r.recorded_seconds >= NO_SPEECH_TIMEOUT:
            r.stop()
            r.close()
            self._set_state(IDLE)
            print("○ no speech detected — cancelled", flush=True)
        elif r.recorded_seconds >= MAX_UTTERANCE:
            self._finish_recording("max length")

    @objc.python_method
    def _finish_recording(self, reason: str) -> None:
        samples = self._recorder.stop()
        self._recorder.close()
        self._set_state(PROCESSING)
        print(f"○ stopped ({reason})", flush=True)
        threading.Thread(target=self._process, args=(samples,), daemon=True).start()

    # --- pipeline (worker thread) ---

    @objc.python_method
    def _process(self, samples) -> None:
        import time

        from chatterbot.inject import (
            accessibility_trusted,
            insert_text,
            secure_input_active,
        )

        try:
            t0 = time.perf_counter()
            text = self._transcriber.transcribe(samples)
            print(
                f"  transcribed {len(samples) / 16_000:.1f}s audio "
                f"in {time.perf_counter() - t0:.2f}s: {text!r}"
            )
            if self._cleaner is not None and text:
                from chatterbot.cleanup import frontmost_app_name

                text, status = self._cleaner.clean(text, frontmost_app_name())
                print(f"  ✦ {status}: {text!r}", flush=True)
            if text:
                delivered = []
                if self._settings["copy_to_clipboard"]:
                    # NSPasteboard isn't documented thread-safe — hop to main
                    self.performSelectorOnMainThread_withObject_waitUntilDone_(
                        "copyToClipboard:", text, False
                    )
                    delivered.append("clipboard")
                if self._settings["type_at_cursor"]:
                    if secure_input_active():
                        print("  ⚠ secure input field active — not typing", flush=True)
                    elif not accessibility_trusted():
                        print(
                            "  ⚠ no Accessibility permission — keystrokes are being "
                            "dropped. Grant ChatterBot.app in System Settings → "
                            "Privacy & Security → Accessibility, then relaunch.",
                            flush=True,
                        )
                    else:
                        insert_text(text + " ")
                        delivered.append("typed")
                if not delivered:
                    print("  ⚠ both outputs disabled — text not delivered", flush=True)
        except Exception as e:  # noqa: BLE001 — keep the app alive no matter what
            print(f"  ⚠ error: {e!r}", flush=True)
        finally:
            self._set_state(IDLE)

    def copyToClipboard_(self, text) -> None:
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(str(text), NSPasteboardTypeString)

    # --- icon/state (safe to call from any thread) ---

    @objc.python_method
    def _set_state(self, state: str) -> None:
        self._state = state
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "applyIcon:", None, False
        )

    def applyIcon_(self, _arg) -> None:
        self._apply_icon()

    @objc.python_method
    def _apply_icon(self) -> None:
        self._status_item.button().setImage_(self._icons[self._state])


def run(use_llm: bool = True) -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = ChatterBotApp.alloc().initWithUseLLM_(use_llm)
    app.setDelegate_(delegate)
    app.run()
