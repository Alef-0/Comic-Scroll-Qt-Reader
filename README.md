<p align="center">
  <img src="comic_scroll_reader/assets/csr_app_icon.png" width="128" height="128" alt="Comic Scroll Reader Logo" />
</p>

<h1 align="center">Comic Scroll Reader</h1>

<p align="center">
  <b>A sleek, high-performance desktop reader for comic folders, webtoons, manga, and PDF documents.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue.svg" alt="Version 1.0.0" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/GUI-PyQt6-41CD52.svg?logo=qt&logoColor=white" alt="PyQt6" />
  <img src="https://img.shields.io/badge/PDF_Engine-Google_PDFium-EA4335.svg" alt="PDF Engine" />
  <img src="https://img.shields.io/badge/Linux-.deb%20%7C%20.rpm-A81D33.svg?logo=linux&logoColor=white" alt="Linux Packages" />
  <img src="https://img.shields.io/badge/Windows-.exe_setup-0078D6.svg?logo=windows&logoColor=white" alt="Windows Setup" />
  <img src="https://img.shields.io/badge/macOS-.dmg-000000.svg?logo=apple&logoColor=white" alt="macOS DMG" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License MIT" />
</p>

---

## 📖 Overview

**Comic Scroll Reader** is a fast, distraction-free desktop application crafted specifically for comic lovers, webtoon readers, and manga fans. Unlike generic image viewers that only show isolated files, Comic Scroll Reader seamlessly handles image folders and PDF documents in both **Single Page mode** (default) and **Continuous Vertical Scroll mode**.

Powered by **Python 3**, **PyQt6**, and **Google PDFium**, it combines instant startup, anchored zooming, asynchronous multi-threaded decoding, and memory-bounded rendering to deliver a silky-smooth reading experience.

---

## ✨ Key Features

- 📖 **Single Page Mode (Default)**:
  - Classic page-by-page viewing for traditional comics, manga, and graphic novels.
  - Anchored fit-to-width, fit-to-height, and free zoom with sub-pixel alignment.
- 📜 **Continuous Vertical Scroll Mode**:
  - Read webtoons, manhwa, and long-strip comics without interruptions.
  - Seamless page-to-page stitching with automatic boundary detection and smooth transitions.
  - Switch instantly between Single Page and Continuous Scroll with key <kbd>1</kbd> / <kbd>2</kbd> or a simple **Right Click**.
- ⚡ **Asynchronous Image Pipeline**:
  - Multi-threaded decoding offloads image rendering from the main UI thread.
  - Fast chunking and prefetching ensure zero lag while scrolling through high-resolution chapters.
- 📑 **Native PDF Document Support**:
  - Direct PDF viewing powered by Google PDFium (`pypdfium2`).
  - High-fidelity on-demand page rasterization with bounded memory caching.
- 📁 **Smart Folder & Archive Browsing**:
  - Open any folder containing images directly.
  - Natural numerical sorting (`1, 2, 10` instead of `1, 10, 2`).
- 🖱️ **Fluid Navigation & Anchored Zoom**:
  - Zoom directly to your mouse cursor (`Ctrl + Wheel` or `Ctrl + +/-`).
  - Pan freely across zoomed pages with left-click drag or `Shift + Wheel`.
  - Double-click to instantly reset zoom and position.
- 🎯 **Minimalist Auto-Hiding HUD**:
  - Floating status pill displaying current page, total count, zoom level, and reader controls.
  - Fades out automatically to keep your screen distraction-free (press `H` to toggle).
- 💻 **Cross-Platform Installers**:
  - Native installers available for **Linux** (`.deb` & `.rpm`), **Windows** (`.exe` setup), and **macOS** (`.dmg`).
  - Complete desktop integration: file associations (PDFs and images) and folder context menu ("Open with Comic Scroll Reader").

---

## 🚀 Installation

Pre-built standalone installers are available for Linux, Windows, and macOS. They contain all necessary dependencies (including Qt6 and Google PDFium) with zero manual Python environment configuration required.

### 🐧 Linux

#### Debian / Ubuntu / Linux Mint / Pop!_OS (`.deb`)
```bash
# Install via apt (resolves system dependencies automatically)
sudo apt install ./comic-scroll-reader_1.0.0_amd64.deb

# Or install via dpkg
sudo dpkg -i comic-scroll-reader_1.0.0_amd64.deb
```
Launch from your desktop application menu or via terminal: `comic-scroll-reader`.  
To uninstall: `sudo apt remove comic-scroll-reader`

#### Fedora / RHEL / CentOS / openSUSE (`.rpm`)
```bash
# Install via dnf
sudo dnf install ./comic-scroll-reader-1.0.0-1.x86_64.rpm

# Or install via rpm
sudo rpm -i comic-scroll-reader-1.0.0-1.x86_64.rpm
```

---

### 🪟 Windows (`.exe` Setup)

1. Download **`comic-scroll-reader-1.0.0-setup.exe`**.
2. Run the setup wizard to install Comic Scroll Reader to your `Program Files`.
3. Features:
   - Optional Desktop shortcut and Start Menu entry.
   - File associations for comics, images, and PDFs.
   - Explorer right-click context menu: **"Open with Comic Scroll Reader"** on any folder.
   - Clean uninstaller registered in Windows Settings.

---

### 🍏 macOS (`.dmg`)

1. Download **`Comic-Scroll-Reader-1.0.0.dmg`**.
2. Open the `.dmg` disk image and drag **Comic Scroll Reader.app** into your **Applications** folder.
3. Launch from Launchpad or Spotlight.

---

### 🐍 Running from Source (Any OS)

If you prefer running directly in Python:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Alef-0/Comic-Scroll-Qt-Reader.git
   cd Comic-Scroll-Qt-Reader
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the reader**:
   ```bash
   ./comic-scroll-reader.sh
   # Or directly with Python:
   python3 -m comic_scroll_reader
   ```

---

## 🛠️ Building Installers

You can compile installers for any platform using the unified `build_installers.sh` script or the `Makefile`.

### Options & Flags

```bash
./build_installers.sh [OPTIONS]

  --deb        Build Debian / Ubuntu package (.deb)
  --rpm        Build Red Hat / Fedora package (.rpm)
  --windows    Build Windows installer (.exe setup wizard)
  --mac        Build macOS Disk Image (.dmg)
  --all        Build all target installers supported on current host
  --clean      Clean build and dist directories before packaging
```

### Quick Commands

```bash
# Build Debian .deb package
make deb
# or: ./build_installers.sh --deb

# Build Red Hat / Fedora .rpm package (requires rpmbuild)
make rpm
# or: ./build_installers.sh --rpm

# Build all available host installers
make installers

# Clean build and distribution artifacts
make clean
```

### Windows & macOS Native Builds
- **Windows**: Run `packaging\windows\build_windows.bat` or `packaging\windows\build_windows.ps1` (compiles standalone executable and Inno Setup installer).
- **macOS**: Run `packaging/mac/build_mac.sh` (compiles `.app` bundle and generates `.dmg` disk image).
- **GitHub Actions**: Push a tag (e.g. `git tag v1.0.0 && git push origin v1.0.0`) to trigger `.github/workflows/release.yml`, which builds all 4 installers on their native cloud runners (`ubuntu-latest`, `windows-latest`, `macos-latest`) and uploads them to your GitHub Release!

---

## ⌨️ Keyboard & Mouse Shortcuts

Comic Scroll Reader is designed to be operated entirely via keyboard and mouse without breaking your reading flow. Press <kbd>F1</kbd> inside the app to open the built-in cheatsheet at any time.

### 📖 Reading Navigation

| Shortcut | Action |
| :--- | :--- |
| <kbd>1</kbd> / <kbd>2</kbd> | Switch to **Single Page** (default) / **Continuous Scroll** mode |
| <kbd>→</kbd> / <kbd>↓</kbd> / <kbd>Space</kbd> | Next page / advance view |
| <kbd>←</kbd> / <kbd>↑</kbd> / <kbd>Backspace</kbd> | Previous page |
| <kbd>Home</kbd> / <kbd>End</kbd> | Jump to First / Last page |
| <kbd>Ctrl</kbd> + <kbd>G</kbd> | Open "Go to Page" prompt |
| **Right Click** | Toggle between Single Page and Continuous Scroll |
| **Middle Click** | Advance to next page |

### 🔍 Zoom and Movement

| Shortcut | Action |
| :--- | :--- |
| <kbd>Ctrl</kbd> + **Mouse Wheel** | Smooth zoom in or out centered on cursor |
| <kbd>Ctrl</kbd> + <kbd>+</kbd> / <kbd>-</kbd> | Zoom in / Zoom out |
| <kbd>Ctrl</kbd> + <kbd>0</kbd> | Reset zoom to fit window |
| **Left Drag** | Pan the page or scroll viewport |
| <kbd>Shift</kbd> + **Mouse Wheel** | Pan horizontally while zoomed |
| **Mouse Wheel** | Pan vertically; seamlessly crosses page boundaries |
| **Double Click** | Reset zoom and view position |

### 🗔 Window & Files

| Shortcut | Action |
| :--- | :--- |
| <kbd>Ctrl</kbd> + <kbd>O</kbd> | Open an image file or PDF document |
| <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>O</kbd> | Open a comic / manga folder |
| <kbd>Ctrl</kbd> + <kbd>W</kbd> | Close current document and return to welcome screen |
| <kbd>F11</kbd> / <kbd>F</kbd> | Toggle distraction-free Fullscreen |
| <kbd>H</kbd> | Toggle bottom HUD controls visibility |
| <kbd>F1</kbd> | Open Keyboard & Mouse Shortcuts guide |
| <kbd>Esc</kbd> | Exit fullscreen or close the reader |

---

## 💻 Command-Line Interface (CLI)

Comic Scroll Reader accepts file and folder paths directly as command-line arguments:

```bash
# Open an image folder / comic chapter
comic-scroll-reader /path/to/manga_chapter_01/

# Open a PDF document
comic-scroll-reader /path/to/comic_book.pdf

# Open a specific image
comic-scroll-reader /path/to/cover.webp
```

---

## 📁 Supported Formats

| Category | Formats / Extensions |
| :--- | :--- |
| **Comic Folders** | Any directory containing supported image formats (sorted numerically) |
| **PDF Documents** | `.pdf` (vector & raster, Google PDFium accelerated) |
| **Raster Images** | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.bmp`, `.avif`, `.tiff` |

---

## 🏗️ Project Architecture

```
Comic-Scroll-Qt-Reader/
├── build_installers.sh       # Unified multi-platform installer builder (.deb, .rpm, .exe, .dmg)
├── comic-scroll-reader.sh    # Quick launcher script for source runs
├── Makefile                  # Build targets (make deb, make rpm, make installers, make test)
├── requirements.txt          # Python dependencies (PyQt6, pypdfium2)
├── packaging/                # Multi-platform installer assets
│   ├── comic-scroll-reader.desktop   # FreeDesktop application entry
│   ├── comic-scroll-reader.spec      # PyInstaller bundling spec for Linux
│   ├── com.github.alef0...metainfo.xml # AppStream metadata
│   ├── control.in                    # Debian control template
│   ├── copyright                     # License & copyright notice
│   ├── postinst / postrm             # Debian maintainer scripts
│   ├── rpm/
│   │   └── comic-scroll-reader.spec  # RPM package specification
│   ├── windows/
│   │   ├── installer.iss             # Inno Setup wizard installer script
│   │   ├── comic-scroll-reader-win.spec # PyInstaller Windows spec
│   │   ├── build_windows.bat         # Batch builder for Windows
│   │   └── build_windows.ps1         # PowerShell builder for Windows
│   └── mac/
│       ├── comic-scroll-reader-mac.spec # PyInstaller macOS spec
│       └── build_mac.sh              # macOS DMG builder
├── .github/workflows/
│   └── release.yml           # Automated multi-platform GitHub Release workflow
├── comic_scroll_reader/      # Main application package
│   ├── __main__.py           # CLI entry point & application bootstrap
│   ├── main_window.py        # Main application window & action routing
│   ├── scroll_reader.py      # Continuous vertical scroll view
│   ├── single_viewer.py      # Classic single page view
│   ├── image_pipeline.py     # Asynchronous image decode & cache pipeline
│   ├── pdf_handler.py        # PDFium document loader & page cache
│   ├── hud_overlay.py        # Floating auto-hiding status & control HUD
│   ├── input_controls.py     # Unified mouse and keyboard event handling
│   ├── shortcuts_dialog.py   # Interactive keyboard shortcut reference
│   ├── about_dialog.py       # Styled About dialog
│   ├── welcome_widget.py     # Welcome screen with quick actions
│   ├── resources.py          # Shared paths & metadata
│   └── assets/               # High-resolution application icons
└── tests/                    # Automated test suite (131 tests)
```

---

## 🧪 Testing

Run the test suite using `pytest`:
```bash
make test
```
Or directly:
```bash
PYTHONPATH=. .venv/bin/pytest tests
```

---

## 👥 Credits & Acknowledgements

- **Author**: Alef-0 ([@Alef-0](https://github.com/Alef-0))
- *Vibe coded by Alef_0 through Gemini and ChatGPT*
- **Technologies**:
  - [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - GUI Toolkit
  - [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) - Google PDFium Python bindings
  - [Google PDFium](https://pdfium.googlesource.com/pdfium/) - Open-source PDF engine

---

## 📄 License

This project is licensed under the **MIT License** - see the [packaging/copyright](packaging/copyright) file for details.
