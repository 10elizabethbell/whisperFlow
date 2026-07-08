class Chatterbox < Formula
  desc "Local Wispr Flow clone: on-device dictation with menu-bar UI"
  homepage "https://github.com/10elizabethbell/chatterBox"
  url "https://github.com/10elizabethbell/chatterBox/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "5f126a5cc7f9065e42af963c44b21a815a493948a4e91e589696b45585e8cd66"
  head "https://github.com/10elizabethbell/chatterBox.git", branch: "main"

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
    py_lib = Formula["python@3.12"].opt_lib
    system ENV.cc, "launcher.c",
      "-o", "build/ChatterBox.app/Contents/MacOS/ChatterBox",
      "-L#{py_lib}", "-lpython3.12",
      "-Wl,-rpath,#{py_lib}"

    # Install the .app bundle. launcher.c walks 5 levels up from
    # Contents/MacOS/ChatterBox and expects libexec/ as a sibling of Applications/.
    (prefix/"Applications").install "build/ChatterBox.app"

    # CLI entry point — runs the menu-bar app when launched from the terminal.
    bin.install_symlink libexec/"bin/chatterbox"
  end

  def caveats
    <<~EOS
      First run downloads the ~1.2GB Parakeet model from HuggingFace.

      To launch the menu-bar app:
        chatterbox          (from terminal — mic icon appears in menu bar)
        open "#{opt_prefix}/Applications/ChatterBox.app"   (via Finder / LaunchServices)

      Grant permissions under System Settings → Privacy & Security:
        • Microphone  (auto-prompted on first recording)
        • Accessibility  (add ChatterBox.app manually for keystroke injection)

      The Claude cleanup pass uses your existing Claude Code login — run `claude`
      and /login if you haven't already. No API key needed.
    EOS
  end

  test do
    system libexec/"bin/python3", "-c", "import chatterbox; print('ok')"
  end
end
