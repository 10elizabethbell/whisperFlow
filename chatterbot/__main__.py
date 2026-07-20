"""Entry point.

    chatterbot                  # menu-bar app: click the mic icon to dictate (auto-stops on silence)
    chatterbot --raw            # menu-bar app without the Claude cleanup pass
    chatterbot transcribe FILE  # transcribe a wav/audio file (no mic needed)
    chatterbot type "TEXT"      # wait 3s (focus a target app), then type TEXT at the cursor
    chatterbot clean "TEXT"     # run the Claude cleanup pass on TEXT (no mic needed)
"""

from __future__ import annotations

import sys
import time


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "transcribe":
        run_file(args[1])
    elif args and args[0] == "type":
        run_type(" ".join(args[1:]))
    elif args and args[0] == "clean":
        run_clean(" ".join(args[1:]))
    else:
        from chatterbot.menubar import run

        run(use_llm="--raw" not in args)


def run_file(path: str) -> None:
    from chatterbot.transcriber import Transcriber

    t = Transcriber()
    t0 = time.perf_counter()
    text = t.transcribe_file(path)
    print(f"[{time.perf_counter() - t0:.2f}s] {text}")


def run_type(text: str) -> None:
    from chatterbot.inject import accessibility_trusted, insert_text

    if not accessibility_trusted():
        print(
            "⚠ No Accessibility permission for this process — keystrokes will be "
            "silently dropped.\n  Grant it in System Settings → Privacy & Security "
            "→ Accessibility (add whatever is running this: your terminal, or "
            "ChatterBot.app), then retry."
        )
    print("Focus the target app — typing in 3s ...")
    time.sleep(3)
    insert_text(text)
    print("done")


def run_clean(text: str) -> None:
    from chatterbot.cleanup import Cleaner, frontmost_app_name

    cleaned, status = Cleaner().clean(text, frontmost_app_name())
    print(f"[{status}] {cleaned}")


if __name__ == "__main__":
    main()
