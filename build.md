# Build Guide — PW Video Downloader

## Prerequisites

Install all required Python packages:

```bash
pip install customtkinter pyinstaller pillow
```

> `pillow` is needed for the app icon (app_icon.jpeg). Without it the icon is silently skipped.

---

## External Tools Required

These must be installed **and available in PATH** before building or running:

| Tool | Install | Purpose |
|------|---------|---------|
| [`yt-dlp`](https://github.com/yt-dlp/yt-dlp/releases) | `pip install yt-dlp` or download binary | Downloads video/audio from PW servers |
| [`ffmpeg`](https://ffmpeg.org/download.html) | `sudo apt install ffmpeg` (Linux) / download (Win) | Merges DASH video+audio, muxing, conversion |

### Quick Install on Linux

```bash
# yt-dlp
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

# ffmpeg
sudo apt install ffmpeg
```

### Quick Install on Windows

```powershell
# Using winget
winget install yt-dlp
winget install ffmpeg
```

Or download manually and place `yt-dlp.exe` + `ffmpeg.exe` next to `PW_Downloader.exe`.

---

## Linux — Build Single Binary

```bash
cd /home/parmanand/Desktop/pw_down

pyinstaller --onefile \
  --name "pw_downloader" \
  --add-data "pw_download.py:." \
  --add-data "updated/app_icon.jpeg:updated" \
  --hidden-import PIL \
  --hidden-import PIL.Image \
  --hidden-import PIL._imagingtk \
  --collect-all customtkinter \
  app.py
```

Output: `dist/pw_downloader`

Run it:
```bash
./dist/pw_downloader
```

> `yt-dlp` and `ffmpeg` must be in `/usr/local/bin` or `/usr/bin` — they are **not** bundled inside the binary.

---

## Windows — Build EXE (No Console Window)

Open **Command Prompt** or **PowerShell** in the project folder:

```cmd
cd C:\path\to\pw_down

pyinstaller --onefile --noconsole ^
  --name "PW_Downloader" ^
  --add-data "pw_download.py;." ^
  --add-data "updated\app_icon.jpeg;updated" ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL._imagingtk ^
  --collect-all customtkinter ^
  app.py
```

Output: `dist\PW_Downloader.exe`

> Double-click `dist\PW_Downloader.exe` to launch.  
> Place `yt-dlp.exe` and `ffmpeg.exe` in the **same folder** as the EXE, or add them to system PATH.

---

## Windows — Debug Build (with Console)

```cmd
pyinstaller --onefile ^
  --name "PW_Downloader_debug" ^
  --add-data "pw_download.py;." ^
  --collect-all customtkinter ^
  app.py
```

---

## Using the .spec File (Recommended for repeated builds)

A `pw_downloader.spec` is included. Edit it to add/remove options, then build with:

```bash
pyinstaller pw_downloader.spec
```

**Enhanced spec example** — edit `pw_downloader.spec` to add icon + PIL support:

```python
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('pw_download.py', '.'),
        ('updated/app_icon.jpeg', 'updated'),
    ],
    hiddenimports=['PIL', 'PIL.Image', 'PIL._imagingtk'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pw_downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # set False on Windows to hide console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

---

## Quick Reference

| Platform | Output | Console |
|----------|--------|---------|
| Linux    | `dist/pw_downloader` | Yes |
| Windows (release) | `dist\PW_Downloader.exe` | No (`--noconsole`) |
| Windows (debug)   | `dist\PW_Downloader_debug.exe` | Yes |

---

## Features Included in the Build

| Feature | Dependency | Notes |
|---------|-----------|-------|
| GUI (CustomTkinter) | `customtkinter` | Bundled via `--collect-all customtkinter` |
| App icon | `pillow` (`PIL`) | Loaded from `updated/app_icon.jpeg` |
| Video download | `yt-dlp` (external) | Must be in PATH |
| DASH merge / mux | `ffmpeg` (external) | Must be in PATH |
| Download history | stdlib `json` | Saved in `download_history.json` |
| Queue auto-resume | stdlib `json` | Saved in `queue.json` |
| Config persistence | stdlib `json` | Saved in `config.json` |
| Parallel downloads | stdlib `threading` | Up to 4 simultaneous |
| URL expiry check | stdlib `urllib` | Warns if signed URL is expiring |
| Internet wait | stdlib `socket` | Pauses and retries when offline |
| Temp folder cleanup | stdlib `glob/shutil` | Cleans `/tmp/pw_dash_*`, `/tmp/pw_cf_dash_*` |
| Retry on failure | stdlib | 3 auto-retries per video |

---

## Notes

- On first build, PyInstaller creates `build/`, `dist/`, and a `.spec` file.
- To **rebuild cleanly**: delete `build/` and `dist/` before running PyInstaller.
- Runtime data files (`config.json`, `download_history.json`, `queue.json`) are created **next to the executable**.
- `links.txt` can be anywhere — browse to it at runtime.
- If `pillow` is not installed, the icon is silently skipped (non-fatal).

---

## Distribution Bundle

Copy these alongside the binary when sharing:

```
dist/
  pw_downloader          ← Linux binary  (or PW_Downloader.exe on Windows)
  yt-dlp                 ← or yt-dlp.exe
  ffmpeg                 ← or ffmpeg.exe  (+ ffprobe recommended)
```

That's everything needed to run on a clean machine.


source venv/bin/activate && rm -rf build dist && pyinstaller --onefile --name "pw_downloader" --add-data "pw_download.py:." --add-data "updated /app_icon.jpeg:updated " --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL._imagingtk --collect-all customtkinter app.py
 


 ///////////////////////////
 linux compile process 


cd /home/parmanand/Desktop/pw_down
source venv/bin/activate




rm -rf build dist && pyinstaller --onefile \
  --name "pw_downloader" \
  --add-data "pw_download.py:." \
  --add-data "updated /app_icon.jpeg:updated " \
  --hidden-import PIL \
  --hidden-import PIL.Image \
  --hidden-import PIL._imagingtk \
  --collect-all customtkinter \
  app.py

