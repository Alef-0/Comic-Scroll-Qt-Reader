Name:           comic-scroll-reader
Version:        1.0.0
Release:        1%{?dist}
Summary:        Continuous scroll and single-page reader for comics, manga, and PDFs
License:        MIT
URL:            https://github.com/Alef-0/Comic-Scroll-Qt-Reader
BuildArch:      x86_64

AutoReqProv:    no
Requires:       python3 >= 3.10, (python3-pyqt6 or python3-qt6)

%description
Comic Scroll Reader is a sleek, modern desktop viewer designed specifically
for reading comic folders, webtoons, manga, and PDF documents with seamless
continuous vertical scroll and classic single-page viewing modes.

%install
mkdir -p %{buildroot}/usr/lib/comic-scroll-reader
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/512x512/apps
mkdir -p %{buildroot}/usr/share/pixmaps
mkdir -p %{buildroot}/usr/share/metainfo
mkdir -p %{buildroot}/usr/share/doc/%{name}

# Copy application and vendored libraries
cp -a %{_sourcedir}/comic_scroll_reader %{buildroot}/usr/lib/comic-scroll-reader/
cp -a %{_sourcedir}/pypdfium2 %{buildroot}/usr/lib/comic-scroll-reader/
cp -a %{_sourcedir}/pypdfium2_raw %{buildroot}/usr/lib/comic-scroll-reader/
if [ -d %{_sourcedir}/pypdfium2_cfg ]; then
    cp -a %{_sourcedir}/pypdfium2_cfg %{buildroot}/usr/lib/comic-scroll-reader/
fi

# Launcher script
install -m 755 %{_sourcedir}/comic-scroll-reader %{buildroot}/usr/bin/comic-scroll-reader

cp %{_sourcedir}/comic-scroll-reader.desktop %{buildroot}/usr/share/applications/
cp %{_sourcedir}/csr_app_icon.png %{buildroot}/usr/share/icons/hicolor/512x512/apps/comic-scroll-reader.png
cp %{_sourcedir}/csr_app_icon.png %{buildroot}/usr/share/pixmaps/comic-scroll-reader.png
cp %{_sourcedir}/com.github.alef0.comic_scroll_reader.metainfo.xml %{buildroot}/usr/share/metainfo/
cp %{_sourcedir}/copyright %{buildroot}/usr/share/doc/%{name}/

%post
if [ -x /usr/bin/update-desktop-database ]; then
    /usr/bin/update-desktop-database -q /usr/share/applications || true
fi
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    /usr/bin/gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi

%postun
if [ -x /usr/bin/update-desktop-database ]; then
    /usr/bin/update-desktop-database -q /usr/share/applications || true
fi
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    /usr/bin/gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi

%files
/usr/bin/comic-scroll-reader
/usr/lib/comic-scroll-reader
/usr/share/applications/comic-scroll-reader.desktop
/usr/share/icons/hicolor/512x512/apps/comic-scroll-reader.png
/usr/share/pixmaps/comic-scroll-reader.png
/usr/share/metainfo/com.github.alef0.comic_scroll_reader.metainfo.xml
%doc /usr/share/doc/%{name}/copyright
