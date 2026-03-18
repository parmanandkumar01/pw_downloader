import os, sys, threading, time
from app import DownloadManager, PWDownloaderApp

def main():
    app = PWDownloaderApp()
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com/watch?v=kffacxfA7G4"
    ]
    app._links = urls
    app._sel_var.set("all")
    app._dir_var.set("/tmp")
    app._par_var.set(2)
    
    # Override internet check to start instantly
    import app as app_module
    app_module.check_internet = lambda: True
    
    # Mock pw_download
    import pw_download
    def mock_download_video(url, output_name, resolution, output_dir, stop_event, pause_event, progress_callback, log_callback):
        for i in range(101):
            if stop_event and stop_event.is_set():
                log_callback("Stopped")
                return
            while pause_event and pause_event.is_set():
                if stop_event and stop_event.is_set(): return
                time.sleep(0.1)
            progress_callback({'percent': i, 'speed': '1MB/s', 'eta': '1m', 'status': 'downloading'})
            time.sleep(0.02)
    app_module.pw_download.download_video = mock_download_video
    
    # Start app logic
    threading.Thread(target=app._on_start, daemon=True).start()
    
    # Let it run
    app.after(5000, app.destroy)
    app.mainloop()

if __name__ == '__main__':
    main()
