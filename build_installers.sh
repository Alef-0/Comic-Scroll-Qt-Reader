#!/usr/bin/env bash
# ==============================================================================
# Comic Scroll Reader - Multi-Platform Installer Builder
# Supports: Debian (.deb), Red Hat/Fedora (.rpm), Windows (.exe), macOS (.dmg)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
PACKAGING_DIR="$PROJECT_ROOT/packaging"
BUILD_DIR="$PROJECT_ROOT/build"
DIST_DIR="$PROJECT_ROOT/dist"

PYTHON_BIN=""
if [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "Error: Python 3 not found." >&2
    exit 1
fi

VERSION="$("$PYTHON_BIN" -c "import comic_scroll_reader; print(comic_scroll_reader.__version__)" 2>/dev/null || echo "1.0.0")"
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
case "$ARCH" in
    x86_64) DEB_ARCH="amd64"; RPM_ARCH="x86_64" ;;
    aarch64|arm64) DEB_ARCH="arm64"; RPM_ARCH="aarch64" ;;
    amd64) DEB_ARCH="amd64"; RPM_ARCH="x86_64" ;;
    *) DEB_ARCH="$ARCH"; RPM_ARCH="$ARCH" ;;
esac

show_help() {
    cat << EOF
Comic Scroll Reader - Multi-Platform Installer Builder (v${VERSION})

Usage: ./build_installers.sh [OPTIONS]

Options:
  --deb         Build Debian / Ubuntu package (.deb)
  --rpm         Build Red Hat / Fedora package (.rpm)
  --windows     Build Windows installer (.exe setup wizard)
  --mac         Build macOS Disk Image (.dmg)
  --all         Build all target installers supported on the current host
  --clean       Clean build and dist directories before packaging
  -h, --help    Display this help message

Examples:
  ./build_installers.sh --deb
  ./build_installers.sh --rpm
  ./build_installers.sh --all
EOF
}

ensure_pyinstaller() {
    if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
        echo "PyInstaller not found. Installing into environment..."
        if [ -f "$PROJECT_ROOT/.venv/bin/pip" ]; then
            "$PROJECT_ROOT/.venv/bin/pip" install pyinstaller
        else
            echo "Error: Please install PyInstaller (pip install pyinstaller)." >&2
            exit 1
        fi
    fi
}

clean_build() {
    echo "Cleaning build artifacts..."
    rm -rf "$BUILD_DIR" "$DIST_DIR"
    mkdir -p "$BUILD_DIR" "$DIST_DIR"
}

build_standalone_bundle() {
    ensure_pyinstaller
    local pyinstaller_dist="$BUILD_DIR/pyinstaller_dist"
    local pyinstaller_build="$BUILD_DIR/pyinstaller_build"

    if [ -f "$pyinstaller_dist/comic-scroll-reader/comic-scroll-reader" ]; then
        echo "Reusing existing PyInstaller application bundle..."
        return 0
    fi

    echo "----------------------------------------------------------------------"
    echo " Compiling standalone application bundle with PyInstaller..."
    echo "----------------------------------------------------------------------"
    mkdir -p "$BUILD_DIR" "$DIST_DIR"
    "$PYTHON_BIN" -m PyInstaller \
        --distpath "$pyinstaller_dist" \
        --workpath "$pyinstaller_build" \
        -y \
        "$PACKAGING_DIR/comic-scroll-reader.spec"
}

build_deb() {
    echo "======================================================================"
    echo " Building Debian package (.deb)..."
    echo "======================================================================"

    if ! command -v dpkg-deb >/dev/null 2>&1; then
        echo "Error: 'dpkg-deb' is required but not installed." >&2
        echo "Install it using: sudo apt install dpkg-dev" >&2
        return 1
    fi

    build_standalone_bundle

    local deb_pkg_name="comic-scroll-reader_${VERSION}_${DEB_ARCH}"
    local stage_dir="$BUILD_DIR/deb_stage/$deb_pkg_name"
    local bundle_src="$BUILD_DIR/pyinstaller_dist/comic-scroll-reader"

    rm -rf "$stage_dir"
    mkdir -p \
        "$stage_dir/usr/lib/comic-scroll-reader" \
        "$stage_dir/usr/bin" \
        "$stage_dir/usr/share/applications" \
        "$stage_dir/usr/share/icons/hicolor/512x512/apps" \
        "$stage_dir/usr/share/pixmaps" \
        "$stage_dir/usr/share/metainfo" \
        "$stage_dir/usr/share/doc/comic-scroll-reader" \
        "$stage_dir/DEBIAN"

    # Copy files
    cp -a "$bundle_src/." "$stage_dir/usr/lib/comic-scroll-reader/"
    ln -s "../lib/comic-scroll-reader/comic-scroll-reader" "$stage_dir/usr/bin/comic-scroll-reader"
    cp "$PACKAGING_DIR/comic-scroll-reader.desktop" "$stage_dir/usr/share/applications/"
    cp "$PROJECT_ROOT/comic_scroll_reader/assets/csr_app_icon.png" "$stage_dir/usr/share/icons/hicolor/512x512/apps/comic-scroll-reader.png"
    cp "$PROJECT_ROOT/comic_scroll_reader/assets/csr_app_icon.png" "$stage_dir/usr/share/pixmaps/comic-scroll-reader.png"
    cp "$PACKAGING_DIR/com.github.alef0.comic_scroll_reader.metainfo.xml" "$stage_dir/usr/share/metainfo/"
    cp "$PACKAGING_DIR/copyright" "$stage_dir/usr/share/doc/comic-scroll-reader/copyright"
    cp "$PACKAGING_DIR/postinst" "$stage_dir/DEBIAN/postinst"
    cp "$PACKAGING_DIR/postrm" "$stage_dir/DEBIAN/postrm"

    # Compute size & control
    local installed_size
    installed_size="$(du -sk "$stage_dir/usr" | awk '{print $1}')"
    sed -e "s/@ARCH@/$DEB_ARCH/g" \
        -e "s/@INSTALLED_SIZE@/$installed_size/g" \
        "$PACKAGING_DIR/control.in" > "$stage_dir/DEBIAN/control"

    # Checksums
    (cd "$stage_dir" && find usr -type f -exec md5sum {} + > DEBIAN/md5sums)

    # Permissions
    find "$stage_dir" -type d -exec chmod 755 {} +
    find "$stage_dir" -type f -exec chmod 644 {} +
    find "$stage_dir" -type f -name "*.so*" -exec chmod 755 {} +
    chmod 755 "$stage_dir/usr/lib/comic-scroll-reader/comic-scroll-reader"
    chmod 755 "$stage_dir/DEBIAN/postinst" "$stage_dir/DEBIAN/postrm"
    chmod 644 "$stage_dir/DEBIAN/control" "$stage_dir/DEBIAN/md5sums" "$stage_dir/usr/share/doc/comic-scroll-reader/copyright"

    local output_deb="$DIST_DIR/${deb_pkg_name}.deb"
    dpkg-deb --build --root-owner-group "$stage_dir" "$output_deb"

    echo ">>> Generated Debian package: $output_deb ($(du -h "$output_deb" | awk '{print $1}'))"
}

build_rpm() {
    echo "======================================================================"
    echo " Building Red Hat / Fedora package (.rpm)..."
    echo "======================================================================"

    if ! command -v rpmbuild >/dev/null 2>&1; then
        echo "[INFO] 'rpmbuild' is not installed on this system."
        echo "       To build RPMs locally:"
        echo "         - Ubuntu/Debian: sudo apt install rpm"
        echo "         - Fedora/RHEL:   sudo dnf install rpm-build"
        echo "       You can also push to GitHub where GitHub Actions builds .rpm automatically."
        return 0
    fi

    build_standalone_bundle

    local rpm_topdir="$BUILD_DIR/rpm_stage"
    local rpm_sources="$rpm_topdir/SOURCES"
    rm -rf "$rpm_topdir"
    mkdir -p "$rpm_sources/bundle" "$rpm_topdir/SPECS" "$rpm_topdir/RPMS" "$rpm_topdir/SRPMS" "$rpm_topdir/BUILD" "$rpm_topdir/BUILDROOT"

    cp -a "$BUILD_DIR/pyinstaller_dist/comic-scroll-reader/." "$rpm_sources/bundle/"
    cp "$PACKAGING_DIR/comic-scroll-reader.desktop" "$rpm_sources/"
    cp "$PROJECT_ROOT/comic_scroll_reader/assets/csr_app_icon.png" "$rpm_sources/"
    cp "$PACKAGING_DIR/com.github.alef0.comic_scroll_reader.metainfo.xml" "$rpm_sources/"
    cp "$PACKAGING_DIR/copyright" "$rpm_sources/"
    cp "$PACKAGING_DIR/rpm/comic-scroll-reader.spec" "$rpm_topdir/SPECS/"

    rpmbuild -bb \
        --define "_topdir $rpm_topdir" \
        --define "_sourcedir $rpm_sources" \
        "$rpm_topdir/SPECS/comic-scroll-reader.spec"

    local generated_rpm
    generated_rpm="$(find "$rpm_topdir/RPMS" -name "*.rpm" | head -n 1)"
    if [ -n "$generated_rpm" ] && [ -f "$generated_rpm" ]; then
        cp "$generated_rpm" "$DIST_DIR/"
        local rpm_basename
        rpm_basename="$(basename "$generated_rpm")"
        echo ">>> Generated RPM package: $DIST_DIR/$rpm_basename ($(du -h "$DIST_DIR/$rpm_basename" | awk '{print $1}'))"
    fi
}

build_windows() {
    echo "======================================================================"
    echo " Building Windows Installer (.exe)..."
    echo "======================================================================"

    local os_type
    os_type="$(uname -s)"

    if [[ "$os_type" =~ ^MINGW|^MSYS|^CYGWIN ]]; then
        powershell.exe -ExecutionPolicy Bypass -File "$PACKAGING_DIR/windows/build_windows.ps1"
        return 0
    fi

    if command -v wine >/dev/null 2>&1 && command -v iscc >/dev/null 2>&1; then
        echo "Wine detected. Attempting Windows build via Wine..."
        # Optional Wine execution if configured
    fi

    echo "[INFO] Windows installers (.exe) can be built using:"
    echo "       1. Windows native: Run 'packaging\\windows\\build_windows.bat' or .ps1"
    echo "       2. GitHub Actions: Release workflow automatically compiles the Inno Setup .exe"
}

build_mac() {
    echo "======================================================================"
    echo " Building macOS Installer (.dmg)..."
    echo "======================================================================"

    if [ "$(uname -s)" = "Darwin" ]; then
        bash "$PACKAGING_DIR/mac/build_mac.sh"
    else
        echo "[INFO] macOS DMG disk images must be built on macOS."
        echo "       1. On a Mac: Run 'packaging/mac/build_mac.sh'"
        echo "       2. GitHub Actions: Release workflow automatically compiles .dmg on macos-latest"
    fi
}

# Parse Command Line Arguments
DO_DEB=false
DO_RPM=false
DO_WIN=false
DO_MAC=false

if [ $# -eq 0 ]; then
    # Default behavior: build all possible native installers on host
    case "$(uname -s)" in
        Linux)
            DO_DEB=true
            DO_RPM=true
            ;;
        Darwin)
            DO_MAC=true
            ;;
        MINGW*|MSYS*|CYGWIN*)
            DO_WIN=true
            ;;
        *)
            DO_DEB=true
            ;;
    esac
else
    while [ $# -gt 0 ]; do
        case "$1" in
            --deb) DO_DEB=true; shift ;;
            --rpm) DO_RPM=true; shift ;;
            --windows|--win) DO_WIN=true; shift ;;
            --mac|--macos) DO_MAC=true; shift ;;
            --all)
                DO_DEB=true
                DO_RPM=true
                DO_WIN=true
                DO_MAC=true
                shift
                ;;
            --clean) clean_build; shift ;;
            -h|--help) show_help; exit 0 ;;
            *) echo "Unknown option: $1" >&2; show_help; exit 1 ;;
        esac
    done
fi

mkdir -p "$DIST_DIR"

if [ "$DO_DEB" = true ]; then
    build_deb
fi
if [ "$DO_RPM" = true ]; then
    build_rpm
fi
if [ "$DO_WIN" = true ]; then
    build_windows
fi
if [ "$DO_MAC" = true ]; then
    build_mac
fi

echo "======================================================================"
echo " Packaging completed! Artifacts are available in: $DIST_DIR"
echo "======================================================================"
ls -lh "$DIST_DIR"
