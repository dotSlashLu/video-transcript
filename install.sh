#!/usr/bin/env bash
# install.sh — idempotent installer for video-transcript.
#
# Designed to be run by an agent, not a human:
#   ./install.sh --json                     -> one JSON object on stdout, progress on stderr
#   ./install.sh --yes                      -> install missing Homebrew packages without asking
#   ./install.sh --prefix <dir>             -> where the runtime is copied
#                                              (default ~/.local/share/video-transcript)
#   ./install.sh --bin-dir <dir>            -> where the launcher goes (default ~/.local/bin)
#   ./install.sh --no-install               -> build only, do not copy anything
#   ./install.sh --skill-dir <dir>          -> install the agent skill into <dir>
#                                              (e.g. ~/.claude/skills/video-transcript)
#
# The runtime (cli/ + .build/) is copied out of the repo, so the clone can be
# deleted afterwards and a later `git pull` cannot change what is installed.
#
# Exit codes: 0 = ready, 1 = needs user action, 2 = failed.
set -uo pipefail

JSON=0
ASSUME_YES=0
DO_INSTALL=1
SKILL_DIR=""
PREFIX="${HOME}/.local/share/video-transcript"
BIN_DIR="${HOME}/.local/bin"
while [ $# -gt 0 ]; do
  case "$1" in
    --json) JSON=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --no-install) DO_INSTALL=0 ;;
    --prefix) PREFIX="${2:-}"; shift ;;
    --bin-dir) BIN_DIR="${2:-}"; shift ;;
    --skill-dir) SKILL_DIR="${2:-}"; shift ;;
    --link)
      echo "--link is obsolete: installing is now a real copy, see --prefix/--bin-dir" >&2 ;;
    -h|--help)
      sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO" || exit 2

log() { [ "$JSON" -eq 1 ] && echo "[install] $*" >&2 || echo "[install] $*"; }

CHECKS_FILE="$(mktemp)"
FIXED_FILE="$(mktemp)"
NEEDS_FILE="$(mktemp)"
trap 'rm -f "$CHECKS_FILE" "$FIXED_FILE" "$NEEDS_FILE"' EXIT

# record <name> <status> <detail>   status: ok | fixed | missing | warn
record() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$CHECKS_FILE"; }
fixed()  { printf '%s\n' "$1" >> "$FIXED_FILE"; }
need()   { printf '%s\t%s\n' "$1" "${2:-}" >> "$NEEDS_FILE"; }   # issue <TAB> command

# ---------- 1. platform ----------
VER="$(sw_vers -productVersion 2>/dev/null || echo 0)"
MAJOR="${VER%%.*}"
if [ "${MAJOR:-0}" -ge 26 ] 2>/dev/null; then
  record macos ok "$VER"
else
  record macos warn "$VER < 26 (speech recognition unavailable, OCR still works)"
fi

# ---------- 2. swift toolchain ----------
if command -v swiftc >/dev/null 2>&1; then
  record swiftc ok "$(swiftc --version 2>/dev/null | head -1)"
else
  record swiftc missing "not installed"
  need "Xcode Command Line Tools are required to compile the recognizers" "xcode-select --install"
  NEEDS_SWIFT=1
fi

# ---------- 3. runtime deps ----------
if command -v ffmpeg >/dev/null 2>&1; then
  record ffmpeg ok "$(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"
else
  if command -v brew >/dev/null 2>&1 && [ "$ASSUME_YES" -eq 1 ]; then
    log "installing ffmpeg via Homebrew…"
    if brew install ffmpeg >/dev/null 2>&1; then
      record ffmpeg fixed "installed via brew"
      fixed "ffmpeg (brew install ffmpeg)"
    else
      record ffmpeg missing "brew install failed"
      need "ffmpeg installation failed; run it manually to see the error" "brew install ffmpeg"
    fi
  elif command -v brew >/dev/null 2>&1; then
    record ffmpeg missing "not installed"
    need "ffmpeg is required for frame/audio extraction (Homebrew is available)" "brew install ffmpeg"
  else
    record ffmpeg missing "not installed, Homebrew absent"
    need "ffmpeg is required; install Homebrew first, then ffmpeg" '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" && brew install ffmpeg'
  fi
fi

if command -v python3 >/dev/null 2>&1; then
  record python3 ok "$(python3 -V 2>&1)"
else
  record python3 missing "not installed"
  need "python3 is required for the orchestrator" "xcode-select --install"
fi

if command -v node >/dev/null 2>&1; then
  record node ok "$(node -v 2>/dev/null)"
else
  record node warn "not installed — only needed to resolve media from web pages"
  fixed "local files and direct media URLs still work without node"
fi

# ---------- 4. build ----------
if [ "${NEEDS_SWIFT:-0}" -eq 0 ]; then
  log "compiling recognizers…"
  if make all >/dev/null 2>&1; then
    record build ok ".build/{vocr,transcribe,probe_speech}"
  else
    record build failed "make all returned non-zero"
    ERR="$(make all 2>&1 | tail -3 | tr '\n' ' ')"
    need "compilation failed" "make all  # $ERR"
  fi
else
  record build skipped "swift toolchain missing"
fi

# ---------- 5. speech locales ----------
if [ -x "$REPO/.build/probe_speech" ]; then
  if "$REPO/.build/probe_speech" 2>/dev/null | grep -q "中文支持: supported=true installed=true"; then
    record speech ok "zh installed"
  elif "$REPO/.build/probe_speech" 2>/dev/null | grep -q "中文支持: supported=true installed=false"; then
    record speech ok "supported, model downloads on first use"
  else
    record speech warn "no Chinese locale reported (run make doctor)"
  fi
else
  record speech skipped "probe_speech not built"
fi

# ---------- 6. install the runtime ----------
if [ "$DO_INSTALL" -eq 1 ]; then
  case "$PREFIX" in
    /|""|"$HOME") record install failed "refusing unsafe prefix: '$PREFIX'" ;;
    *)
      if [ -d "$REPO/.build" ] && [ -f "$REPO/cli/video_transcript.py" ]; then
        mkdir -p "$PREFIX"
        rm -rf "$PREFIX/cli" "$PREFIX/.build"
        cp -R "$REPO/cli" "$PREFIX/cli"
        cp -R "$REPO/.build" "$PREFIX/.build"
        rm -rf "$PREFIX/cli/__pycache__"
        mkdir -p "$BIN_DIR"
        rm -f "$BIN_DIR/video-transcript"   # never write through a pre-existing symlink
        cat > "$BIN_DIR/video-transcript" <<LAUNCHER
#!/usr/bin/env bash
exec python3 "$PREFIX/cli/video_transcript.py" "\$@"
LAUNCHER
        chmod +x "$BIN_DIR/video-transcript"
        record install ok "$PREFIX"
        fixed "copied runtime into $PREFIX"
        case ":$PATH:" in
          *":$BIN_DIR:"*) record cli ok "$BIN_DIR/video-transcript" ;;
          *)
            record cli warn "$BIN_DIR/video-transcript — $BIN_DIR is not on PATH"
            need "$BIN_DIR is not on PATH, so 'video-transcript' will not resolve" \
                 "export PATH=\"$BIN_DIR:\$PATH\"  # then reload your shell" ;;
        esac
      else
        record install failed "build artifacts missing; run make first"
      fi ;;
  esac
else
  record install skipped "--no-install: use ./video-transcript from the repo"
fi

# ---------- 7. skill for the agent ----------
if [ -n "$SKILL_DIR" ]; then
  if [ -f "$REPO/skill/SKILL.md" ]; then
    mkdir -p "$SKILL_DIR"
    cp -R "$REPO/skill/." "$SKILL_DIR/"
    record skill ok "$SKILL_DIR"
    fixed "installed skill/ (SKILL.md + references) into $SKILL_DIR"
  else
    record skill failed "skill/SKILL.md missing from repo"
  fi
else
  record skill skipped "no --skill-dir given (skill not installed for the agent)"
fi

# ---------- report ----------
python3 - "$CHECKS_FILE" "$FIXED_FILE" "$NEEDS_FILE" "$REPO" "$JSON" <<'PY'
import json, sys, pathlib

checks_f, fixed_f, needs_f, repo, as_json = sys.argv[1:6]
checks = []
for line in pathlib.Path(checks_f).read_text().splitlines():
    name, status, detail = (line.split("\t") + ["", ""])[:3]
    checks.append({"name": name, "status": status, "detail": detail})

fixed = [l for l in pathlib.Path(fixed_f).read_text().splitlines() if l]
needs = []
for line in pathlib.Path(needs_f).read_text().splitlines():
    issue, _, cmd = line.partition("\t")
    needs.append({"issue": issue, "command": cmd})

blocking = [c for c in checks if c["status"] in ("missing", "failed")]
ready = not blocking and any(c["name"] == "build" and c["status"] == "ok" for c in checks)

report = {
    "ok": ready,
    "ready": ready,
    "repo": repo,
    "checks": checks,
    "fixed": fixed,
    "needs_user": needs,
    "skill_installed": any(c["name"] == "skill" and c["status"] == "ok" for c in checks),
    "next": ("./video-transcript <url-or-file>" if ready
             else "resolve needs_user, then rerun ./install.sh --json"),
}
if ready and not report["skill_installed"]:
    report["hint"] = "CLI works; rerun with --skill-dir <your skills dir> to install the agent skill"
if as_json == "1":
    print(json.dumps(report, ensure_ascii=False, indent=2))
else:
    print(f"\nvideo-transcript @ {repo}")
    for c in checks:
        mark = {"ok": "✓", "fixed": "✓", "missing": "✗", "failed": "✗", "warn": "!", "skipped": "-"}[c["status"]]
        print(f"  {mark} {c['name']:<10} {c['detail']}")
    if needs:
        print("\nNeeds you:")
        for n in needs:
            print(f"  · {n['issue']}")
            if n["command"]:
                print(f"    $ {n['command']}")
    print(f"\n{'Ready.' if ready else 'Not ready.'}  {report['next']}")
    if ready and not report["skill_installed"]:
        print("  hint: rerun with --skill-dir <your skills dir> to install the agent skill")

sys.exit(0 if ready else 1)
PY
exit $?
