# PW Video Downloader - Learning Roadmap

This roadmap is designed to help you master all the tools, libraries, and technologies used in the PW Video Downloader project. It is structured from beginner to advanced levels.

---

## Phase 1: Python Core & Advanced Concepts (Weeks 1-2)
*The foundation of the entire project.*

### 1. Advanced Python Basics
- **File I/O:** Reading/writing text and JSON files (`open()`, `json.load()`, `json.dump()`).
- **Data Structures:** Lists, Dictionaries, Tuples, and Sets.
- **Exception Handling:** `try`, `except`, `finally`, and creating custom exceptions.
- **String Manipulation:** Advanced string formatting and slicing.

### 2. Regular Expressions (`re` module)
- Understanding regex patterns to extract data (e.g., URLs, percentages, ETAs from strings).
- Functions to master: `re.search()`, `re.match()`, `re.findall()`, `re.sub()`.

### 3. Concurrency & Threading (`threading` & `concurrent.futures`)
- **Threading:** Creating threads, Daemon threads, and Thread synchronization using `threading.Lock()` and `threading.Event()`.
- **Thread Pools:** Using `concurrent.futures.ThreadPoolExecutor` for parallel downloading.
- **Queueing:** Using the `queue.Queue` module for thread-safe job management.

---

## Phase 2: Web Scraping & Networking (Weeks 3-4)
*Interacting with APIs and downloading streams over the internet.*

### 1. HTTP Requests (`urllib` & `requests`)
- Making GET/POST requests.
- Handling HTTP Headers (User-Agent, Authorization, Cookies).
- Downloading large files in chunks (`stream=True` in `requests`).
- Handling timeouts, 403 (Forbidden), and 404 (Not Found) errors.

### 2. URL and Network Modules
- **`urllib.parse`:** Parsing URLs, extracting query parameters (`urlparse`, `parse_qs`, `urlencode`).
- **`socket`:** Basic network checks (e.g., checking internet connectivity).

### 3. Basic HTTP Server (`http.server`)
- Creating a local proxy server using `BaseHTTPRequestHandler` and `HTTPServer`.
- Intercepting and rewriting HTTP responses (used in the project to modify `.m3u8` files on the fly).

---

## Phase 3: Video Streaming Technologies (Weeks 5-6)
*Understanding how PW streams video and how to capture it.*

### 1. HLS (HTTP Live Streaming)
- What is an `.m3u8` master playlist and media playlist.
- Understanding `.ts` (Transport Stream) video segments.
- AES-128 Encryption in HLS and how the decryption key works.

### 2. DASH (Dynamic Adaptive Streaming over HTTP)
- Understanding the `.mpd` (Media Presentation Description) XML file.
- Parsing XML files using Python's `xml.etree.ElementTree`.
- ClearKey CENC (Common Encryption) basics.
- Separated audio and video streams (muxing).

---

## Phase 4: External CLI Tools (Weeks 7-8)
*The workhorses of the backend script.*

### 1. The `subprocess` Module
- Running external commands from Python (`subprocess.run`, `subprocess.Popen`).
- Capturing `stdout` and `stderr` in real-time to update progress bars.
- Managing background processes (terminating/killing them).

### 2. yt-dlp
- Command-line arguments for downloading HLS streams.
- Bypassing SSL checks, handling retries, and merging formats.
- **Key Args:** `--hls-use-mpegts`, `--merge-output-format mp4`, `--concurrent-fragments`.

### 3. FFmpeg
- Basics of video/audio processing.
- Concatenating video segments.
- Merging (Muxing) separate video and audio files without re-encoding (`-c copy`).
- Decrypting encrypted streams using `-decryption_key`.

---

## Phase 5: GUI Development with CustomTkinter (Weeks 9-10)
*Building the beautiful, dark-themed user interface.*

### 1. CustomTkinter Basics
- Setting up the main window (`ctk.CTk`).
- Grids, Packs, and Layout Management (`grid()`, `pack()`, `place()`).
- Themes and Appearance modes (Dark/Light).

### 2. GUI Widgets
- `CTkFrame`, `CTkScrollableFrame`, `CTkToplevel` (for popup windows)
- Buttons, Labels, Entries, and StringVars (`tk.StringVar()`).
- `CTkProgressBar` for showing video/audio download progress.

### 3. Pillow (PIL)
- Loading, resizing, and displaying images/icons in the UI (`Image`, `ImageTk`).

---

## Phase 6: Packaging and Deployment (Week 11)
*Turning your Python scripts into standalone executable files.*

### 1. PyInstaller
- Compiling Python scripts to single binaries (`--onefile`).
- Hiding the console window on Windows (`--noconsole`).
- Bundling external assets like images and other Python scripts (`--add-data`).
- Resolving hidden imports (e.g., for PIL).

### 2. PyInstaller `.spec` Files
- Customizing the build process using a `.spec` file.
- Handling PyInstaller's temporary `_MEIPASS` directory at runtime to locate bundled assets.

---

## Next Steps / How to Practice
1. **Start Small:** Write a script that just reads URLs from `links.txt` and parses them using `urllib.parse`.
2. **Build a Tiny GUI:** Create a CustomTkinter window with one Button and a Progress Bar.
3. **Download a Public Video:** Use `subprocess` and `yt-dlp` to download a non-encrypted YouTube video.
4. **Combine:** Connect your tiny GUI to the download script and update the progress bar inside a Thread.
