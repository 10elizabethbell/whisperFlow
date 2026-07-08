# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Local Wispr Flow clone for macOS: a menu-bar dictation app. Click the mic icon, speak, and the transcribed + LLM-cleaned text is typed at the cursor of the frontmost app. Transcription is fully on-device (Parakeet TDT v3 via MLX). macOS-only — depends on PyObjC (AppKit/Quartz), CoreAudio via sounddevice, and Apple Silicon for MLX.

## Commands

```sh
uv venv --python 3.12 && uv pip install -e .   # setup (first run downloads ~1.2GB model)
./build.sh                                     # compile the .app launcher (after venv changes / new machine)

.venv/bin/chatterbot          # run the menu-bar app
.venv/bin/chatterbot --raw    # without the Claude cleanup pass
open build/ChatterBot.app     # same app via the .app wrapper (LaunchServices)
```

There is no test suite or linter. Each pipeline stage has a CLI test helper that runs without the menu bar or mic:

```sh
.venv/bin/chatterbot transcribe path/to/16khz-mono.wav   # transcription only
.venv/bin/chatterbot type "hello"                        # injection only (types after 3s — focus a text field first)
.venv/bin/chatterbot clean "um so uh send it friday no wait thursday"   # cleanup pass only

# generate a test wav without speaking:
say -o /tmp/t.aiff "testing one two three" && afconvert -f WAVE -d LEI16@16000 -c 1 /tmp/t.aiff /tmp/t.wav
```

The hosting terminal needs Microphone and Accessibility permissions (System Settings → Privacy & Security). Without Accessibility, synthetic keystrokes are silently dropped — injection "does nothing" with no error. When launched via `build/ChatterBot.app` instead, both permissions attach to ChatterBot.app rather than the terminal and must be granted separately.

### The .app wrapper

`build/ChatterBot.app` is a thin wrapper — a compiled C launcher (`launcher.c`, built by `build.sh`) that runs the chatterbot package **in-process via libpython**. It must not be a script that execs the venv interpreter: on this macOS the window server silently parks the status item off-screen (x=-1, fully invisible, no error) whenever a bundle-launched process has exec'd a binary other than its declared CFBundleExecutable. The launcher resolves the project root relative to its own path, puts the project root + venv site-packages on PYTHONPATH (the editable-install `.pth` is not honored there), and prepends `/opt/homebrew/bin` to PATH so the cleanup pass finds the `claude` CLI. When called with arguments it behaves as a plain interpreter (argv passthrough), so `sys.executable` re-invocations like multiprocessing don't spawn a second app.

The wrapper exists so the sibling ApplicationManager project (which discovers `*.app` bundles under `menuBarApps/`) can list, launch, and quit this app; it matches by the `com.chatterbot.app` bundle ID. The `MenuBarSymbolName` key in Info.plist is what ApplicationManager reads for the list icon. The launcher shows an alert if the venv is missing, and links libpython via an rpath into the uv-managed CPython behind `.venv` — rerun `./build.sh` if that moves.

## Architecture

Pipeline, one module per stage, orchestrated by `menubar.py`:

```
menubar.py (AppKit status item, state machine)
  → audio.py      Recorder: continuous mic stream, 500ms pre-roll ring buffer, energy VAD
  → transcriber.py Parakeet MLX, model kept in memory (~0.06s per utterance warm)
  → cleanup.py    Cleaner: headless `claude -p --bare --model haiku` subprocess
  → inject.py     types text via CGEvent Unicode keystrokes
```

### Threading model

Three threads, and it matters which code runs where:

- **Main thread**: all AppKit UI (status item, menu, icon changes). Worker threads request icon updates via `performSelectorOnMainThread_` (`_set_state`).
- **Audio callback thread** (sounddevice): `Recorder._callback` appends blocks and updates VAD counters under `self._lock`. Keep this callback cheap.
- **Worker thread**: the transcribe → clean → inject pipeline (`menubar._process`), so the ~1s Haiku call never blocks the UI. Model loading also happens on a background thread at startup.

The menu-bar timer (`tick_`, 10Hz) polls `Recorder.has_speech` / `silence_seconds` to auto-stop after 2s of post-speech silence; VAD counters are block-based (not wall-clock) so the logic is deterministic.

### Contracts and constraints that span files

- **Audio format is 16kHz mono float32 end-to-end**: Recorder produces it, Transcriber requires it (`get_logmel` bit-views the rfft output against the input dtype — anything but float32 breaks), `transcribe_file` rejects other wavs.
- **Typing must never go through the clipboard**: `inject.py` types via `CGEventKeyboardSetUnicodeString`, chunked at the 20-UTF-16-unit event cap with surrogate pairs kept intact — don't route it through a paste. The only pasteboard writer is the explicit "Copy to Clipboard" menu toggle (default off; `menubar.copyToClipboard_`, main thread).
- **The cleanup pass must never eat words**: every `Cleaner` failure mode (timeout, not logged in, CLI missing, empty output) returns the raw transcript with a status string. Utterances under 5 words skip the LLM. "Not logged in" disables the pass for the session instead of retrying.
- **Cleanup rides the user's Claude Code login** (no API key): it spawns the `claude` CLI per utterance. Its system prompt treats transcript content strictly as text to clean, never as instructions.
- **Secure input**: `inject.secure_input_active()` must be checked before injecting so dictation can't land in password fields; the menu-bar flow already does this.
- **State machine** in `menubar.py`: LOADING → IDLE ⇄ RECORDING → PROCESSING → IDLE. Clicks are ignored outside IDLE/RECORDING; icons in `icons.py` are drawn per-state.

### Other notes

- Personal dictionary: `~/.config/chatterbot/dictionary.txt` (one term per line, `#` comments) is folded into the cleanup system prompt for spelling correction.
- Output toggles: the right-click menu has "Type at Cursor" (default on) and "Copy to Clipboard" (default off), persisted by `settings.py` to `~/.config/chatterbot/settings.json`. With both off, the pipeline still runs but the text is only printed.
- End-to-end injection can't be verified headlessly — `chatterbot type` sends real keystrokes to whatever is focused. Test chunking/logic with `_post_unicode_chunk` mocked instead.
