#!/usr/bin/env bash
# =============================================================================
# BARJ Volume Controller — Manager
# Single command to install, update, or uninstall.
#
# Install flow:
#   1. Check dependencies (system components + Python packages)
#   2. List which are installed or missing
#   3. Ask whether to proceed
#   4. Ask for the admin password — only if something actually needs root
#   5. Download + install (with a live, single-line-per-bar progress display)
#   6. Finish and print the install + config locations
#
# Usage:
#   chmod +x manage.sh && ./manage.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

say()     { echo -e "$*"; }
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
die()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
blank()   { echo ""; }

# Overall progress: each install/update step calls step_header to print
# "[ Step N of TOTAL ]" so the user can see how far along the whole process is.
STEP_NUM=0
STEP_TOTAL=6
step_begin() { STEP_NUM=0; STEP_TOTAL="${1:-6}"; }
step_header() {
    STEP_NUM=$((STEP_NUM + 1))
    blank
    echo -e "${BOLD}${CYAN}[ Step ${STEP_NUM} of ${STEP_TOTAL} ]${RESET} ${BOLD}$*${RESET}"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null || echo /tmp)"
APP_NAME="barj-volume-controller"
APP_DISPLAY="BARJ Volume Controller"
DEFAULT_INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/$APP_NAME"
PYTHON_BIN="python3"
REPO_URL="https://github.com/JoeRAB/BARJ-Volume-Controller"
REPO_BRANCH="main"

NEED_SUDO=false
NEEDS_RELOGIN=false

# When run via `curl … | bash`, the script has no repo beside it. Detect that
# (no main.py next to us) and fetch the project into a temp dir first, then
# re-exec the bundled manage.sh from there so install copies real files.
bootstrap_if_needed() {
    [[ -f "$SCRIPT_DIR/main.py" ]] && return   # running from a real checkout

    say "${BOLD}${CYAN}BARJ Volume Controller — quick installer${RESET}"
    blank
    info "Fetching the latest version from GitHub…"

    local tmp
    tmp="$(mktemp -d)"
    if command -v git &>/dev/null; then
        git clone --depth 1 -b "$REPO_BRANCH" "$REPO_URL" "$tmp/src" 2>/dev/null \
            || die "git clone failed. Check your connection or the repo URL."
        SRC="$tmp/src"
    elif command -v curl &>/dev/null; then
        curl -fL --progress-bar "$REPO_URL/archive/refs/heads/$REPO_BRANCH.tar.gz" \
            -o "$tmp/src.tar.gz" || die "Download failed."
        mkdir -p "$tmp/src" && tar -xzf "$tmp/src.tar.gz" -C "$tmp/src" --strip-components=1
        SRC="$tmp/src"
    else
        die "Need either git or curl installed to fetch the project."
    fi

    [[ -f "$SRC/manage.sh" ]] || die "Fetched archive is missing manage.sh."
    chmod +x "$SRC/manage.sh"
    success "Downloaded to a temporary folder."
    blank
    # Re-run the downloaded manager. Redirect stdin from the terminal so its
    # prompts work even though we were started via `curl ... | bash`.
    if [[ -e /dev/tty ]]; then
        exec bash "$SRC/manage.sh" "$@" </dev/tty
    else
        exec bash "$SRC/manage.sh" "$@"
    fi
}

# =============================================================================
# UTILITY
# =============================================================================

# Returns 0 (true) if a valid install exists at the given path
is_install() {
    local path="$1"
    [[ -f "$path/main.py" ]] && [[ -d "$path/venv" ]]
}

detect_pkg_mgr() {
    if   command -v apt-get &>/dev/null; then echo "apt"
    elif command -v dnf     &>/dev/null; then echo "dnf"
    elif command -v pacman  &>/dev/null; then echo "pacman"
    elif command -v zypper  &>/dev/null; then echo "zypper"
    else echo "none"
    fi
}

# Try to install a single system package; report the outcome on one line.
try_pkg() {
    local mgr="$1" pkg="$2"
    case "$mgr" in
        apt)
            if apt-cache show "$pkg" &>/dev/null 2>&1; then
                if sudo apt-get install -y "$pkg" -qq; then
                    echo -e "    ${GREEN}✓${RESET} $pkg"
                else
                    echo -e "    ${YELLOW}⚠${RESET} $pkg (failed, continuing)"
                fi
            else
                echo -e "    ${YELLOW}⊘${RESET} $pkg (not available)"
            fi ;;
        dnf)
            if sudo dnf install -y "$pkg" --quiet 2>/dev/null; then
                echo -e "    ${GREEN}✓${RESET} $pkg"
            else
                echo -e "    ${YELLOW}⊘${RESET} $pkg (not available)"
            fi ;;
        pacman)
            if sudo pacman -S --noconfirm "$pkg" 2>/dev/null; then
                echo -e "    ${GREEN}✓${RESET} $pkg"
            else
                echo -e "    ${YELLOW}⊘${RESET} $pkg (not available)"
            fi ;;
        zypper)
            if sudo zypper install -y "$pkg" 2>/dev/null; then
                echo -e "    ${GREEN}✓${RESET} $pkg"
            else
                echo -e "    ${YELLOW}⊘${RESET} $pkg (not available)"
            fi ;;
    esac
}

# Check if a Python package is importable. Prefer the existing venv's Python
# (that's where the app actually runs); fall back to system Python otherwise.
pip_check() {
    local py="$PYTHON_BIN"
    if [[ -n "${CHECK_DIR:-}" ]] && [[ -x "$CHECK_DIR/venv/bin/python" ]]; then
        py="$CHECK_DIR/venv/bin/python"
    fi
    "$py" -c "import $1" 2>/dev/null
}

# =============================================================================
# SYSTEM-COMPONENT CHECKS  (the things that may need root to install)
# =============================================================================
# Each component is tested by trying to import the relevant module(s) with the
# SYSTEM python3 — because the venv is created with --system-site-packages, so
# whatever system python3 can import, the venv can import too.

sys_test_venv()  { "$PYTHON_BIN" -c "import ensurepip, venv" 2>/dev/null; }
sys_test_tk()    { "$PYTHON_BIN" -c "import tkinter" 2>/dev/null; }
sys_test_gi()    { "$PYTHON_BIN" -c "import gi" 2>/dev/null; }
sys_test_appindicator() {
    "$PYTHON_BIN" - <<'PY' 2>/dev/null
import gi
for name, ver in (("AyatanaAppIndicator3", "0.1"), ("AppIndicator3", "0.1")):
    try:
        gi.require_version(name, ver)
        __import__("gi.repository." + name)
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        pass
raise SystemExit(1)
PY
}

# apt package(s) that satisfy each system component, by index.
sys_apt_pkgs_for() {
    case "$1" in
        0) echo "python3-venv python3-pip" ;;
        1) echo "python3-tk" ;;
        2) echo "python3-gi gir1.2-gtk-3.0" ;;
        3) echo "gir1.2-ayatana-appindicator3-0.1" ;;   # handled specially (variants)
    esac
}
sys_dnf_pkgs_for() {
    case "$1" in
        0) echo "python3-pip" ;;
        1) echo "python3-tkinter" ;;
        2) echo "python3-gobject gtk3" ;;
        3) echo "libayatana-appindicator-gtk3" ;;
    esac
}
sys_pacman_pkgs_for() {
    case "$1" in
        0) echo "python-pip" ;;
        1) echo "tk" ;;
        2) echo "python-gobject gtk3" ;;
        3) echo "libayatana-appindicator" ;;
    esac
}
sys_zypper_pkgs_for() {
    case "$1" in
        0) echo "python3-pip" ;;
        1) echo "python3-tk" ;;
        2) echo "python3-gobject gtk3" ;;
        3) echo "libayatana-appindicator3-1 typelib-1_0-AyatanaAppIndicator3-0_1" ;;
    esac
}

check_system_deps() {
    SYS_NAMES=("Python venv (installer)" "tkinter (GUI toolkit)" \
               "GTK / GObject (tray)"    "AppIndicator (tray icon)")
    local tests=(sys_test_venv sys_test_tk sys_test_gi sys_test_appindicator)
    SYS_STATUS=(); SYS_MISSING_IDX=(); SYS_ANY_MISSING=false
    local i
    for i in "${!SYS_NAMES[@]}"; do
        if ${tests[$i]}; then
            SYS_STATUS+=("installed")
        else
            SYS_STATUS+=("missing")
            SYS_MISSING_IDX+=("$i")
            SYS_ANY_MISSING=true
        fi
    done
}

# =============================================================================
# DEP CHECK + LISTING  (shared by install and update) — checks, lists, no prompt
# =============================================================================

run_dep_check() {
    # When updating an existing install, check the venv where the app actually
    # runs (not system Python). Pass the install dir in.
    CHECK_DIR="${1:-}"

    # Python packages (installed into the venv via pip).
    DEP_NAMES=(  "pyserial"  "PyYAML"  "pulsectl"  "pystray"  "Pillow"  "psutil" )
    DEP_IMPORTS=( "serial"   "yaml"    "pulsectl"  "pystray"  "PIL"     "psutil" )
    DEP_PKGS=(   "pyserial"  "pyyaml"  "pulsectl"  "pystray"  "Pillow"  "psutil" )
    DEP_STATUS=(); PIP_ANY_MISSING=false

    # --- System components ---
    check_system_deps

    blank
    say "${BOLD}Checking dependencies…${RESET}"
    blank
    say "  ${BOLD}System components${RESET} (need root to install):"
    local i
    for i in "${!SYS_NAMES[@]}"; do
        if [[ "${SYS_STATUS[$i]}" == "installed" ]]; then
            printf "    %-26s ${GREEN}Installed${RESET}\n" "${SYS_NAMES[$i]}"
        else
            printf "    %-26s ${YELLOW}Missing${RESET}\n" "${SYS_NAMES[$i]}"
        fi
    done

    blank
    say "  ${BOLD}Python packages${RESET} (installed into the app's virtual env):"
    for i in "${!DEP_NAMES[@]}"; do
        if pip_check "${DEP_IMPORTS[$i]}"; then
            DEP_STATUS+=("installed")
            printf "    %-26s ${GREEN}Installed${RESET}\n" "${DEP_NAMES[$i]}"
        else
            DEP_STATUS+=("missing")
            PIP_ANY_MISSING=true
            printf "    %-26s ${YELLOW}Missing${RESET}\n" "${DEP_NAMES[$i]}"
        fi
    done

    # Summary counts
    local n_sys=0 n_pip=0
    for s in "${SYS_STATUS[@]}";  do [[ "$s" == "missing" ]] && n_sys=$((n_sys+1)); done
    for s in "${DEP_STATUS[@]}";  do [[ "$s" == "missing" ]] && n_pip=$((n_pip+1)); done
    blank
    if (( n_sys == 0 && n_pip == 0 )); then
        info "Everything is already installed."
    else
        say "  ${BOLD}Missing:${RESET} ${n_sys} system component(s), ${n_pip} Python package(s)."
    fi
}

# Ask once for the admin password, but ONLY if something actually needs root:
# either a system component is missing, or the user isn't yet in the serial
# group. If nothing needs root, no password is requested.
ensure_sudo_if_needed() {
    local need_group=false grp=""
    for g in dialout uucp; do
        if getent group "$g" &>/dev/null; then grp="$g"; break; fi
    done
    if [[ -n "$grp" ]] && ! groups "$USER" | grep -qw "$grp"; then
        need_group=true
    fi
    SERIAL_GROUP="$grp"
    NEED_GROUP="$need_group"

    if [[ "$SYS_ANY_MISSING" == true || "$need_group" == true ]]; then
        NEED_SUDO=true
        blank
        say "  ${BOLD}Administrator access is required to:${RESET}"
        [[ "$SYS_ANY_MISSING" == true ]] && say "    • install the missing system components"
        [[ "$need_group" == true ]]      && say "    • add you to the '${grp}' group for serial-port access"
        blank
        if ! sudo -v; then
            die "Could not obtain administrator access. No changes made."
        fi
        success "Administrator access granted."
    else
        NEED_SUDO=false
        info "No administrator access needed — all system components are present."
    fi
}

# =============================================================================
# DOWNLOAD PROGRESS HELPERS  (single line per bar, updated in place)
# =============================================================================

_human_bytes() {
    awk -v b="${1:-0}" 'BEGIN{
        if (b >= 1073741824) printf "%.2f GB", b/1073741824;
        else if (b >= 1048576) printf "%.1f MB", b/1048576;
        else if (b >= 1024)    printf "%.0f KB", b/1024;
        else printf "%d B", b
    }'
}

_progress_bar() {   # $1=percent  $2=width
    local pct="${1:-0}" width="${2:-18}" filled empty i out=""
    if (( pct < 0 ));   then pct=0;   fi
    if (( pct > 100 )); then pct=100; fi
    filled=$(( pct * width / 100 ))
    empty=$(( width - filled ))
    out="["
    for (( i=0; i<filled; i++ )); do out+="="; done
    if (( filled < width )); then out+=">"; empty=$(( empty - 1 )); fi
    for (( i=0; i<empty; i++ )); do out+=" "; done
    out+="]"
    printf '%s' "$out"
}

_filesize() {
    if [[ -f "$1" ]]; then stat -c%s "$1" 2>/dev/null || echo 0; else echo 0; fi
}

# Repaint the two progress lines in place (current package + cumulative total).
_render_two() {  # name cur fsize cum total idx count
    local name="$1" cur="$2" fsize="$3" cum="$4" total="$5" idx="$6" count="$7"
    local fpct=0 tpct=0
    if (( fsize > 0 )); then fpct=$(( cur * 100 / fsize )); fi
    if (( total > 0 )); then tpct=$(( cum * 100 / total )); fi
    if (( fpct > 100 )); then fpct=100; fi
    if (( tpct > 100 )); then tpct=100; fi
    local l1 l2
    l1="$(printf '  %-16.16s %s %9s / %-9s %3d%%' \
        "$name" "$(_progress_bar "$fpct" 16)" \
        "$(_human_bytes "$cur")" "$(_human_bytes "$fsize")" "$fpct")"
    l2="$(printf '  %-16s %s %9s / %-9s %3d%%  (%d/%d)' \
        "Total" "$(_progress_bar "$tpct" 16)" \
        "$(_human_bytes "$cum")" "$(_human_bytes "$total")" "$tpct" "$idx" "$count")"
    printf '\033[2A\r\033[K%s\n\r\033[K%s\n' "$l1" "$l2"
}

# Resolve the exact files pip would download (with sizes) for the given
# packages. Prints tab-separated lines, each with a leading tag so the two row
# types stay unambiguous and no field is ever empty:
#   PKG<TAB>size<TAB>name<TAB>url   - one per package to download
#   TOTAL<TAB>sum                   - the grand total download size
# Returns non-zero if resolution isn't possible (e.g. an older pip without
# --report), so the caller can fall back to a plain pip install.
_resolve_downloads() {
    local vpy="$1" report="$2"; shift 2
    if ! "$vpy" -m pip install --dry-run --quiet --no-input \
            --report "$report" "$@" >/dev/null 2>&1; then
        return 1
    fi
    "$vpy" - "$report" <<'PY'
import json, sys, urllib.request, os
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)

items = []
for entry in data.get("install", []):
    di = entry.get("download_info") or {}
    url = di.get("url")
    meta = entry.get("metadata") or {}
    name = meta.get("name") or "package"
    if url:
        items.append((name, url))

def head_size(url):
    try:
        if url.startswith("file://"):
            return os.path.getsize(urllib.request.url2pathname(url[7:]))
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as r:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl else 0
    except Exception:
        return 0

# Output format (tab-separated, NO empty fields so `read` with IFS=tab can't
# collapse them): per package -> "PKG<TAB>size<TAB>name<TAB>url"; then a final
# total line -> "TOTAL<TAB>sum". Size and sum are always numeric (never empty);
# name and url are always present. A leading tag keeps the two row types
# unambiguous regardless of field widths.
total = 0
out = []
for name, url in items:
    sz = head_size(url)
    total += sz
    out.append(f"PKG\t{sz}\t{name}\t{url}")
out.append(f"TOTAL\t{total}")
sys.stdout.write("\n".join(out) + "\n")
PY
}

# Plain pip install, used if the live-progress path can't run.
_pip_fallback() {
    local vpip="$1"; shift
    warn "Falling back to standard pip output."
    local pkg
    for pkg in "$@"; do
        echo -e "  ${CYAN}→${RESET} ${BOLD}$pkg${RESET}"
        if "$vpip" install "$pkg" --progress-bar on --no-input; then
            echo -e "    ${GREEN}✓${RESET} $pkg"
        else
            echo -e "    ${YELLOW}⚠${RESET} $pkg (failed)"
        fi
    done
}

# =============================================================================
# INSTALL STEPS  (called by both install and update)
# =============================================================================

step_system_packages() {
    local mgr="$1"
    step_header "Installing system components"

    if [[ "$SYS_ANY_MISSING" != true ]]; then
        echo -e "    ${GREEN}✓${RESET} All required system components already present."
        return
    fi
    if [[ "$mgr" == "none" ]]; then
        warn "No supported package manager found."
        warn "Install manually: tkinter, python3-gi, GTK 3, and an AppIndicator library."
        return
    fi

    [[ "$mgr" == "apt" ]] && sudo apt-get update -qq

    local idx pkg
    for idx in "${SYS_MISSING_IDX[@]}"; do
        if [[ "$idx" == "3" ]]; then
            # AppIndicator: package name differs across distros/versions. Try the
            # common variants and stop at the first that installs.
            local got=false
            case "$mgr" in
                apt)
                    for pkg in gir1.2-ayatana-appindicator3-0.1 \
                               gir1.2-appindicator3-0.1; do
                        if apt-cache show "$pkg" &>/dev/null 2>&1; then
                            if sudo apt-get install -y "$pkg" -qq; then
                                echo -e "    ${GREEN}✓${RESET} $pkg"; got=true; break
                            fi
                        fi
                    done ;;
                *)
                    for pkg in $(sys_${mgr}_pkgs_for 3); do
                        if try_pkg "$mgr" "$pkg" | grep -q "✓"; then got=true; fi
                    done
                    got=true ;;   # best-effort on non-apt
            esac
            $got || echo -e "    ${YELLOW}⊘${RESET} AppIndicator (not found — tray may not show on all desktops)"
        else
            for pkg in $(sys_${mgr}_pkgs_for "$idx"); do
                try_pkg "$mgr" "$pkg"
            done
        fi
    done
}

step_venv() {
    local install_dir="$1"
    step_header "Creating Python virtual environment"
    [[ -d "$install_dir/venv" ]] && rm -rf "$install_dir/venv"

    # --system-site-packages lets the venv import the apt-installed GTK /
    # AppIndicator bindings (python3-gi, gir1.2-ayatana-appindicator3-0.1).
    # Without this, pystray can't load its AppIndicator backend and the tray
    # icon falls back to an unresponsive backend.
    if ! "$PYTHON_BIN" -m venv --system-site-packages "$install_dir/venv" 2>/dev/null; then
        local py_ver
        py_ver=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        warn "Retrying after installing python${py_ver}-venv…"
        [[ "$(detect_pkg_mgr)" == "apt" ]] \
            && sudo apt-get install -y "python${py_ver}-venv" -qq
        "$PYTHON_BIN" -m venv --system-site-packages "$install_dir/venv" \
            || die "Cannot create the virtual environment."
    fi
    success "Virtual environment ready (with system site-packages for tray support)."
}

step_pip() {
    local install_dir="$1"
    step_header "Installing Python packages"
    local vpy="$install_dir/venv/bin/python"
    local vpip="$install_dir/venv/bin/pip"

    # Upgrade pip quietly so the dependency resolver/report is current.
    "$vpip" install --upgrade pip --quiet --no-input 2>/dev/null || true

    local pkgs=("${DEP_PKGS[@]}")
    local cache report
    cache="$(mktemp -d)"; report="$(mktemp)"

    # Resolve the download list + sizes. If unavailable, fall back to plain pip.
    local resolved
    if ! resolved="$(_resolve_downloads "$vpy" "$report" "${pkgs[@]}")"; then
        rm -rf "$cache" "$report" 2>/dev/null || true
        _pip_fallback "$vpip" "${pkgs[@]}"
        return
    fi
    rm -f "$report" 2>/dev/null || true

    # Parse the resolver output. Each line is tab-separated with a leading tag:
    #   PKG <size> <name> <url>   - a package to download
    #   TOTAL <sum>               - the grand total size
    # No field is ever empty, so `read` with IFS=tab can't collapse columns.
    # Arrays are initialised empty (=()) so ${#arr[@]} is safe under `set -u`
    # even when nothing is appended (the "all already satisfied" case).
    local -a names=() sizes=() urls=()
    local total=0 tag a b c
    while IFS=$'\t' read -r tag a b c; do
        case "$tag" in
            PKG)   sizes+=("$a"); names+=("$b"); urls+=("$c") ;;
            TOTAL) total="$a" ;;
        esac
    done <<< "$resolved"

    if (( ${#urls[@]} == 0 )); then
        echo -e "    ${GREEN}✓${RESET} All Python packages already satisfied (nothing to download)."
        rm -rf "$cache" 2>/dev/null || true
        return
    fi

    echo -e "  ${BOLD}To download:${RESET} ${#urls[@]} package(s)   ${BOLD}Total size:${RESET} $(_human_bytes "$total")"
    blank

    local use_ansi=false
    [[ -t 1 ]] && use_ansi=true
    $use_ansi && printf '\n\n'   # reserve the two progress lines

    local done_bytes=0 i rc final cur
    for i in "${!urls[@]}"; do
        local name="${names[$i]}" url="${urls[$i]}" fsize="${sizes[$i]}"
        local fname dest
        fname="$(basename "${url%%\?*}")"
        dest="$cache/$fname"

        # Background download; the subshell writes its exit code to a sentinel
        # file on completion (robust completion signal — no zombie polling).
        ( curl -fsSL "$url" -o "$dest"; echo $? > "$dest.rc" ) &
        local cpid=$!

        if $use_ansi; then
            while [[ ! -f "$dest.rc" ]]; do
                cur=$(_filesize "$dest")
                _render_two "$name" "$cur" "$fsize" \
                            "$(( done_bytes + cur ))" "$total" "$((i+1))" "${#urls[@]}"
                sleep 0.1
            done
        else
            while [[ ! -f "$dest.rc" ]]; do sleep 0.2; done
        fi

        rc=$(cat "$dest.rc" 2>/dev/null || echo 1); rm -f "$dest.rc"
        wait "$cpid" 2>/dev/null || true

        if (( rc != 0 )); then
            $use_ansi && printf '\n'
            echo -e "    ${YELLOW}⚠${RESET} Download failed for $name — switching to standard pip."
            rm -rf "$cache" 2>/dev/null || true
            _pip_fallback "$vpip" "${pkgs[@]}"
            return
        fi

        final=$(_filesize "$dest"); done_bytes=$(( done_bytes + final ))
        if $use_ansi; then
            _render_two "$name" "$final" "$fsize" \
                        "$done_bytes" "$total" "$((i+1))" "${#urls[@]}"
        else
            echo -e "    ${GREEN}✓${RESET} $name ($(_human_bytes "$final"))"
        fi
    done
    $use_ansi && printf '\n'
    blank

    # Install from the wheels we just downloaded — offline, fast, and quiet.
    echo -e "  ${CYAN}→${RESET} Installing ${#urls[@]} package(s) from the download cache…"
    if "$vpip" install --no-index --find-links "$cache" --no-input --quiet "${pkgs[@]}" 2>/dev/null; then
        echo -e "    ${GREEN}✓${RESET} All Python packages installed."
    else
        _pip_fallback "$vpip" "${pkgs[@]}"
    fi
    rm -rf "$cache" 2>/dev/null || true
}

step_copy_files() {
    local install_dir="$1"
    step_header "Copying application files"
    # Remove previously-installed app code first so renamed/deleted modules
    # don't linger and cause stale-import bugs. The venv and config are left
    # untouched (config lives elsewhere entirely).
    for old in main.py serial_reader.py config_manager.py autostart.py \
               app_detector.py single_instance.py tray_icon.py \
               requirements.txt README.md audio gui arduino; do
        [[ -e "$install_dir/$old" ]] && rm -rf "$install_dir/$old"
    done
    for item in main.py serial_reader.py config_manager.py autostart.py \
                tray_icon.py requirements.txt README.md audio gui arduino; do
        local src="$SCRIPT_DIR/$item"
        if [[ -e "$src" ]]; then
            cp -r "$src" "$install_dir/"
            echo -e "    ${GREEN}✓${RESET} $item"
        else
            echo -e "    ${YELLOW}⊘${RESET} $item (not found in $SCRIPT_DIR)"
        fi
    done
}

step_launcher() {
    local install_dir="$1"
    step_header "Creating launcher and app-menu entry"

    mkdir -p "$BIN_DIR" "$DESKTOP_DIR"

    cat > "$BIN_DIR/$APP_NAME" << LAUNCHER
#!/usr/bin/env bash
exec "$install_dir/venv/bin/python" "$install_dir/main.py" "\$@"
LAUNCHER
    chmod +x "$BIN_DIR/$APP_NAME"
    echo -e "    ${GREEN}✓${RESET} Launcher: $BIN_DIR/$APP_NAME"

    cat > "$DESKTOP_DIR/$APP_NAME.desktop" << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_DISPLAY
Comment=Hardware volume controller with Arduino potentiometers
Exec=$BIN_DIR/$APP_NAME
Icon=audio-volume-high
Terminal=false
Categories=AudioVideo;Audio;Utility;
Keywords=volume;mixer;audio;arduino;barj;
StartupNotify=true
DESKTOP
    chmod +x "$DESKTOP_DIR/$APP_NAME.desktop"
    command -v update-desktop-database &>/dev/null \
        && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    echo -e "    ${GREEN}✓${RESET} App-menu entry"

    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        warn "~/.local/bin is not in PATH. Add to ~/.bashrc:"
        warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
}

step_serial_group() {
    step_header "Configuring serial-port access"
    local grp="${SERIAL_GROUP:-}"
    if [[ -z "$grp" ]]; then
        for g in dialout uucp; do
            if getent group "$g" &>/dev/null; then grp="$g"; break; fi
        done
    fi
    if [[ -z "$grp" ]]; then
        warn "No dialout/uucp group found on this system."
    elif groups "$USER" | grep -qw "$grp"; then
        echo -e "    ${GREEN}✓${RESET} Already in group '$grp'"
    else
        sudo usermod -aG "$grp" "$USER"
        echo -e "    ${GREEN}✓${RESET} Added to group '$grp'"
        NEEDS_RELOGIN=true
    fi
}

print_summary() {
    local install_dir="$1"
    blank
    say "${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
    say "${BOLD}${GREEN}║              All Done!                   ║${RESET}"
    say "${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
    blank
    say "  ${BOLD}Launch:${RESET}"
    say "    ${CYAN}barj-volume-controller${RESET}           (normal)"
    say "    ${CYAN}barj-volume-controller --debug${RESET}   (show raw Arduino values)"
    blank
    say "  ${BOLD}Application files installed to:${RESET}"
    say "    ${CYAN}$install_dir${RESET}"
    blank
    say "  ${BOLD}Configuration and profiles:${RESET}"
    say "    ${CYAN}$CONFIG_DIR/config.yaml${RESET}"
    say "    ${GREEN}(Never modified by this script)${RESET}"
    blank
    if [[ "${NEEDS_RELOGIN:-false}" == true ]]; then
        say "  ${YELLOW}⚠  Log out and back in for serial-port access to take effect.${RESET}"
        blank
    fi
    say "  First run: click ${BOLD}⚙ Settings${RESET} and select your serial port."
    say "  Common ports:  /dev/ttyACM0   /dev/ttyUSB0"
    blank
}

# =============================================================================
# ACTIONS
# =============================================================================

do_install() {
    local install_dir="$1"
    local pkg_mgr
    pkg_mgr=$(detect_pkg_mgr)

    # Validate Python
    command -v "$PYTHON_BIN" &>/dev/null || die "python3 not found."
    local py_ver major minor
    py_ver=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    major="${py_ver%%.*}"; minor="${py_ver#*.}"
    if [[ "$major" -lt 3 || ( "$major" -eq 3 && "$minor" -lt 10 ) ]]; then
        die "Python 3.10+ required (found $py_ver)."
    fi

    say "  ${BOLD}Install location:${RESET}  ${CYAN}$install_dir${RESET}"
    say "  ${BOLD}Config location:${RESET}   ${CYAN}$CONFIG_DIR/config.yaml${RESET}"

    # 1 + 2: check dependencies and list them
    run_dep_check "$install_dir"

    # 3: ask whether to proceed
    blank
    read -rp "$(echo -e "${BOLD}Proceed with installation? [Y/n]: ${RESET}")" ans </dev/tty
    case "${ans,,}" in
        n|no) blank; say "${YELLOW}Cancelled. No changes made.${RESET}"; exit 0 ;;
    esac

    # Verify the target is usable before asking for a password.
    if ! mkdir -p "$install_dir" 2>/dev/null; then
        die "Cannot create '$install_dir' (permission denied).
       Choose a location inside your home folder, or pre-create it:
       sudo mkdir -p '$install_dir' && sudo chown \$USER '$install_dir'"
    fi
    if [[ ! -w "$install_dir" ]]; then
        die "'$install_dir' is not writable by your user.
       Pick a path in your home folder, or fix ownership:
       sudo chown -R \$USER '$install_dir'"
    fi

    # 4: ask for the password — only if something needs root
    ensure_sudo_if_needed

    # 5: download + install
    NEEDS_RELOGIN=false
    step_begin 6
    step_system_packages "$pkg_mgr"
    step_venv            "$install_dir"
    step_pip             "$install_dir"
    step_copy_files      "$install_dir"
    step_launcher        "$install_dir"
    step_serial_group

    # 6: finish + locations
    print_summary "$install_dir"
}

do_update() {
    local install_dir="$1"
    local pkg_mgr
    pkg_mgr=$(detect_pkg_mgr)

    say "  ${BOLD}Updating installation at:${RESET}"
    say "    ${CYAN}$install_dir${RESET}"
    if [[ -f "$CONFIG_DIR/config.yaml" ]]; then
        say "  ${BOLD}Config found — will not be touched:${RESET}"
        say "    ${CYAN}$CONFIG_DIR/config.yaml${RESET}"
    fi

    run_dep_check "$install_dir"

    blank
    read -rp "$(echo -e "${BOLD}Proceed with update? [Y/n]: ${RESET}")" ans </dev/tty
    case "${ans,,}" in
        n|no) blank; say "${YELLOW}Update cancelled. No changes made.${RESET}"; exit 0 ;;
    esac

    ensure_sudo_if_needed

    NEEDS_RELOGIN=false
    step_begin 6
    step_system_packages "$pkg_mgr"
    step_venv            "$install_dir"
    step_pip             "$install_dir"
    step_copy_files      "$install_dir"
    step_launcher        "$install_dir"
    step_serial_group

    print_summary "$install_dir"
}

do_uninstall() {
    local install_dir="$1"

    # Clean BOTH the passed-in dir AND the default location so no stray folders
    # are left behind (which previously caused false "update" detection).
    local -a remove_dirs=() remove_files=()
    remove_dirs+=("$DEFAULT_INSTALL_DIR")
    if [[ "$install_dir" != "$DEFAULT_INSTALL_DIR" ]]; then
        remove_dirs+=("$install_dir")
    fi
    remove_files+=("$BIN_DIR/$APP_NAME")
    remove_files+=("$DESKTOP_DIR/$APP_NAME.desktop")

    blank
    say "${BOLD}The following will be removed:${RESET}"
    for d in "${remove_dirs[@]}";  do [[ -e "$d" ]] && say "  ${CYAN}$d${RESET}"; done
    for f in "${remove_files[@]}"; do [[ -e "$f" ]] && say "  ${CYAN}$f${RESET}"; done
    blank

    local del_config="n"
    if [[ -d "$CONFIG_DIR" ]]; then
        say "  ${BOLD}Your config and profiles are at:${RESET}"
        say "  ${CYAN}$CONFIG_DIR${RESET}"
        blank
        say "  Keeping them means a future reinstall restores your profiles."
        read -rp "$(echo -e "${BOLD}Keep config and profiles? [Y/n]: ${RESET}")" keep_cfg </dev/tty
        blank
        case "${keep_cfg,,}" in
            n|no) del_config="y" ;;
            *)    del_config="n" ;;
        esac
    fi

    read -rp "$(echo -e "${BOLD}Proceed with uninstall? [y/N]: ${RESET}")" ans </dev/tty
    blank
    case "${ans,,}" in
        y|yes) ;;
        *) say "Uninstall cancelled."; exit 0 ;;
    esac

    for d in "${remove_dirs[@]}"; do
        if [[ -d "$d" ]]; then rm -rf "$d" && success "Removed: $d"; fi
    done
    for f in "${remove_files[@]}"; do
        if [[ -e "$f" ]]; then rm -f "$f" && success "Removed: $f"; fi
    done

    command -v update-desktop-database &>/dev/null \
        && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

    if [[ "${del_config,,}" == "y" ]]; then
        [[ -d "$CONFIG_DIR" ]] && rm -rf "$CONFIG_DIR" && success "Removed: $CONFIG_DIR"
    else
        blank
        say "  ${GREEN}Config kept at:${RESET}"
        say "  ${CYAN}$CONFIG_DIR${RESET}"
        say "  Reinstalling will pick it back up automatically."
    fi

    blank
    say "${BOLD}${GREEN}BARJ Volume Controller has been fully uninstalled.${RESET}"
    blank
}

# =============================================================================
# PATH PROMPTS + MENU
# =============================================================================

ask_for_custom_path() {
    blank
    say "  Enter the full path to your BARJ Volume Controller installation."
    say "  Example:  /home/joe/.local/share/barj-volume-controller"
    say "  (Press Tab to autocomplete the path)"
    blank
    read -rep "$(echo -e "${BOLD}Path: ${RESET}")" custom_path </dev/tty
    blank
    custom_path="${custom_path/#\~/$HOME}"
    if [[ -z "$custom_path" ]]; then
        say "${YELLOW}No path entered. Returning to main menu.${RESET}"; return 1
    fi
    if is_install "$custom_path"; then
        success "Installation found at: $custom_path"; return 0
    else
        warn "No BARJ Volume Controller installation found at: $custom_path"
        blank
        read -rp "$(echo -e "${BOLD}Install here instead? [Y/n]: ${RESET}")" ans_install_here </dev/tty
        case "${ans_install_here,,}" in
            n|no) say "Returning to menu."; return 1 ;;
            *)    do_install "$custom_path"; exit 0 ;;
        esac
    fi
}

ask_for_install_path() {
    blank
    say "  ${BOLD}Enter the directory to install BARJ Volume Controller into.${RESET}"
    say "  The folder will be created if it doesn't exist."
    say "  Example:  /opt/barj   or   ~/apps/barj-volume-controller"
    say "  (Press Tab to autocomplete the path)"
    blank
    read -rep "$(echo -e "${BOLD}Install path: ${RESET}")" install_target </dev/tty
    blank
    install_target="${install_target/#\~/$HOME}"
    if [[ -z "$install_target" ]]; then
        say "${YELLOW}No path entered. Returning to menu.${RESET}"; return 1
    fi
    if is_install "$install_target"; then
        warn "An installation already exists at: $install_target"
        read -rp "$(echo -e "${BOLD}Update it instead of reinstalling? [Y/n]: ${RESET}")" ans_up </dev/tty
        case "${ans_up,,}" in
            n|no) : ;;
            *)    do_update "$install_target"; exit 0 ;;
        esac
    fi
    return 0
}

main() {
    bootstrap_if_needed "$@"

    if [[ ! -e /dev/tty ]]; then
        die "No terminal available for input. Run this script directly in a terminal:
       git clone $REPO_URL && cd BARJ-Volume-Controller && ./manage.sh"
    fi

    clear
    blank
    say "${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
    say "${BOLD}${CYAN}║   BARJ Volume Controller — Manager       ║${RESET}"
    say "${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
    blank

    FOUND_DIR=""
    if is_install "$DEFAULT_INSTALL_DIR"; then
        FOUND_DIR="$DEFAULT_INSTALL_DIR"
    fi

    if [[ -n "$FOUND_DIR" ]]; then
        say "  ${GREEN}Installation found:${RESET}"
        say "    ${CYAN}$FOUND_DIR${RESET}"
        blank
        say "  What would you like to do?"
        blank
        say "    1)  Update"
        say "    2)  Uninstall"
        say "    3)  Cancel"
        blank
        read -rp "$(echo -e "${BOLD}Enter choice [1/2/3]: ${RESET}")" choice </dev/tty
        blank
        case "$choice" in
            1) do_update    "$FOUND_DIR" ;;
            2) do_uninstall "$FOUND_DIR" ;;
            3) say "Cancelled."; exit 0 ;;
            *) say "${YELLOW}Invalid choice.${RESET}"; exit 1 ;;
        esac
    else
        say "  ${YELLOW}No installation found at the default location.${RESET}"
        blank
        say "  What would you like to do?"
        blank
        say "    1)  Install  (to $DEFAULT_INSTALL_DIR)"
        say "    2)  Install to a custom location"
        say "    3)  Provide a path to an existing installation"
        say "    4)  Cancel"
        blank
        read -rp "$(echo -e "${BOLD}Enter choice [1/2/3/4]: ${RESET}")" choice </dev/tty
        blank
        case "$choice" in
            1) do_install "$DEFAULT_INSTALL_DIR" ;;
            2) if ask_for_install_path; then do_install "$install_target"; fi ;;
            3)
                if ask_for_custom_path; then
                    blank
                    say "  What would you like to do?"
                    blank
                    say "    1)  Update"
                    say "    2)  Uninstall"
                    say "    3)  Cancel"
                    blank
                    read -rp "$(echo -e "${BOLD}Enter choice [1/2/3]: ${RESET}")" choice2 </dev/tty
                    blank
                    case "$choice2" in
                        1) do_update    "$custom_path" ;;
                        2) do_uninstall "$custom_path" ;;
                        3) say "Cancelled."; exit 0 ;;
                        *) say "${YELLOW}Invalid choice.${RESET}"; exit 1 ;;
                    esac
                fi
                ;;
            4) say "Cancelled."; exit 0 ;;
            *) say "${YELLOW}Invalid choice.${RESET}"; exit 1 ;;
        esac
    fi
}

main "$@"
