# Comprehensive Refactoring and Bug Fix Prompt for `pw_down`

I have a Python desktop GUI application (`app.py`) for downloading videos, and a backend script (`pw_download.py`) that downloads DASH video and audio segments from a CDN. I need you to refactor the code to fix several issues and implement some enhancements.

Here are the details of the problems and what needs to be fixed.

## Part 1: Segment Downloading Enhancements (Backend: `pw_download.py`)

Currently, the script downloads DASH segments sequentially (all video segments, then all audio segments).
**The Problem:** For large videos, the download takes too long. Because the CDN uses temporary signed URLs with a strict expiration time, the URL often expires before the script finishes downloading the audio track. This results in standard video players freezing in the middle of playback and the final video completely missing its audio at the end, due to 403 Forbidden errors once the URL expires.

**The Solution Required:**
1. Refactor the segment downloading logic to use parallel downloading using `concurrent.futures.ThreadPoolExecutor`.
2. Download multiple segments concurrently to drastically speed up the download and beat the expiration timer.
3. Interleave the downloading of video and audio segments so they progress together.
4. Ensure the progress callback and terminal output still accurately reflect the overall progress.
5. Update the `download_dash` and `_cloudfront_manual_dash` functions while keeping the decryption and ffmpeg muxing intact.

## Part 2: GUI and Integration Bug Fixes (Frontend: `app.py` & Backend: `pw_download.py`)

Several new features like Parallel Downloads Support (1 to 10 concurrent video downloads via `ThreadPoolExecutor`) and a Multi-Progress Cards UI were recently introduced in the GUI. However, this update introduced several critical bugs:

1. **Broken Output Interceptor (Logs / Progress Not Showing):**
   - **The Issue:** The attempt to fix capturing `print()` logs for multiple threads used `threading.local()`, but it only set a local property and never actually overrode the global `sys.stdout`.
   - **Fix Required:** Ensure that any `print()` called inside the `pw_download.py` backend is correctly forwarded to the GUI, so the UI accurately displays download progress instead of reporting "no activity download".

2. **"Cancel Downloads" Logic is Broken:**
   - **The Issue:** The new worker loop instantly empties the initial `_queue` and pushes all tasks straight into the `ThreadPoolExecutor`.
   - **Fix Required:** When "Stop" is clicked, it completely fails to cancel tasks because the queue is immediately empty. Correct the cancellation logic so that pending and running jobs in the thread pool can be properly stopped and canceled by the user.

3. **Progress Bar Glitches on Job Finish:**
   - **The Issue:** Destroying individual progress cards via `self._prog_cards[name].destroy()` happens without proper un-packing. When a job is finished, the individual progress UI immediately vanishes instead of lingering at 100%.
   - **Fix Required:** Gracefully handle the completion state of individual progress cards so it looks smooth (e.g., linger at 100% briefly or show a success state before disappearing).

4. **Annoying Terminal/Console Windows Popping Up (Windows/Desktop):**
   - **The Issue:** The backend `pw_download.py` script uses `subprocess.Popen` and `subprocess.run` to call external tools like `yt-dlp` and `ffmpeg`. Executing these commands from a GUI app without hiding the console window causes multiple black command prompt windows to flash open and steal focus.
   - **Fix Required:** Use `creationflags=subprocess.CREATE_NO_WINDOW` (on Windows) or equivalent configuration to suppress these console popups completely so they run silently in the background.

5. **`yt-dlp` and `ffmpeg` Missing After Compile (PyInstaller Issue):**
   - **The Issue:** The updated code fails to properly bundle or execute `yt-dlp` and `ffmpeg` when compiled into a standalone executable. It fails to extract them from the PyInstaller temporary `_MEIPASS` directory during execution.
   - **Fix Required:** Implement a robust path resolution using `sys._MEIPASS` (or `get_resource_path`) to correctly locate and execute bundled `yt-dlp` and `ffmpeg` binaries.

6. **Setting App Icon (`app_icon.jpg`):**
   - **The Issue:** The application's icon needs to be set using `app_icon.jpg` from the `updated` folder.
   - **Fix Required:** Properly load `app_icon.jpg` (possibly using Pillow `PIL.ImageTk` and `wm_iconbitmap` or `.iconphoto()`) and set it as the window icon for the Tkinter/CustomTkinter GUI.

Please analyze the current code and provide the necessary corrections for all the points listed above.
also add soluction  from itself if any possible of error