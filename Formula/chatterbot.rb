class Chatterbot < Formula
  desc "Local Wispr Flow clone: on-device dictation with menu-bar UI"
  homepage "https://github.com/10elizabethbell/chatterBot"
  url "https://github.com/10elizabethbell/chatterBot/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "ec3c7c0a962848e1e5d27594efcc7649b6736927b6c2e4dbb96dee41eb58f78c"
  head "https://github.com/10elizabethbell/chatterBot.git", branch: "main"

  depends_on "python@3.12"
  depends_on arch: :arm64 # MLX requires Apple Silicon

  def install
    # Build a virtualenv in libexec and install the package + deps from PyPI.
    # launcher.c detects this location at runtime (libexec/lib/python3.12/site-packages).
    python3 = Formula["python@3.12"].opt_bin/"python3.12"
    system python3, "-m", "venv", libexec
    system libexec/"bin/pip", "install", "--quiet", "--upgrade", "pip"
    system libexec/"bin/pip", "install", "--quiet", "."

    # Rebuild the C launcher to link against homebrew's Python (not uv's).
    # Homebrew builds Python as a macOS framework: libpython3.12.dylib lives
    # under Frameworks/, not opt_lib (which only has pkgconfig + stdlib dir).
    py_lib = Formula["python@3.12"].opt_frameworks/"Python.framework/Versions/3.12/lib"
    (buildpath/"build/ChatterBot.app/Contents/MacOS").mkpath
    system ENV.cc, "launcher.c",
      "-o", "build/ChatterBot.app/Contents/MacOS/ChatterBot",
      "-L#{py_lib}", "-lpython3.12",
      "-Wl,-rpath,#{py_lib}"

    # Install the .app bundle. launcher.c walks 5 levels up from
    # Contents/MacOS/ChatterBot and expects libexec/ as a sibling of Applications/.
    (prefix/"Applications").install "build/ChatterBot.app"

    # CLI entry point — runs the menu-bar app when launched from the terminal.
    bin.install_symlink libexec/"bin/chatterbot"
  end

  def caveats
    <<~EOS
      First run downloads the ~1.2GB Parakeet model from HuggingFace.

      To launch the menu-bar app:
        chatterbot          (from terminal — mic icon appears in menu bar)
        open "#{opt_prefix}/Applications/ChatterBot.app"   (via Finder / LaunchServices)

      Grant permissions under System Settings → Privacy & Security:
        • Microphone  (auto-prompted on first recording)
        • Accessibility  (add ChatterBot.app manually for keystroke injection)

      The Claude cleanup pass uses your existing Claude Code login — run `claude`
      and /login if you haven't already. No API key needed.
    EOS
  end

  test do
    system libexec/"bin/python3", "-c", "import chatterbot; print('ok')"
    # Exercise the compiled launcher via its argv passthrough — this loads
    # libpython through the rpath and would catch a bad link, which the
    # venv import above cannot.
    system opt_prefix/"Applications/ChatterBot.app/Contents/MacOS/ChatterBot",
           "-c", "import chatterbot; print('ok')"
  end
end
