<p align="center">
  <img src="comic_scroll_reader/assets/csr_app_icon.png" width="128" height="128" alt="Comic Scroll Reader Logo" />
</p>

<h1 align="center">Comic Scroll Reader</h1>

<p align="center">
  <b>Desktop reader for comic folders, webtoons, manga, and PDF documents.</b>
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
