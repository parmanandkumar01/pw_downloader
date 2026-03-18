# Windows Setup Guide — PW Video Downloader

## Step 1: Python Install करें

1. [python.org](https://www.python.org/downloads/) पर जाएं
2. Latest Python download करें
3. Install करते वक्त **✅ "Add Python to PATH"** ज़रूर check करें
4. VS Code open करें → Terminal (`Ctrl + ~`) → check करें:
   ```
   python --version
   ```

---

## Step 2: Dependencies Install करें

VS Code Terminal में (project folder में):

```
pip install -r requirements.txt
```

---

## Step 3: mitmproxy Certificate Setup (एक बार करना है)

1. `launch_sniffer.bat` **double-click** करें (Firefox खुलेगा)
2. Firefox में जाएं: `http://mitm.it`
3. **Windows** वाला certificate download करके install करें
4. Firefox बंद करें → `launch_sniffer.bat stop` terminal में type करें

---

## Step 4: Firefox Profile Setup (एक बार)

Firefox में proxy set करें:
- Settings → Network Settings → Manual Proxy
- HTTP Proxy: `127.0.0.1` Port: `8080`
- "Also use for HTTPS" ✅ check करें

---

## Daily Use — Videos Download करने के लिए

### Step A: Sniffer चलाएं
```
launch_sniffer.bat
```
या double-click करें `launch_sniffer.bat`

### Step B: Video Play करें
- Firefox में PW website खोलें
- जो video download करनी है उसे play करें
- URL अपने आप `links.txt` में save हो जाएगी

### Step C: Video Download करें
```
launch_pw_downloader.bat
```
या double-click करें `launch_pw_downloader.bat`

- Prefix पूछेगा (e.g. `Lecture`)
- Resolution पूछेगा (e.g. `720`)
- Video download होकर same folder में save होगी

### Step D: Sniffer बंद करें
```
launch_sniffer.bat stop
```

---

## Files की जानकारी

| File | काम |
|------|-----|
| `launch_sniffer.bat` | Sniffer + Firefox start करता है |
| `launch_pw_downloader.bat` | links.txt से videos download करता है |
| `links.txt` | Captured video URLs |
| `pw_download.py` | Main downloader script |
| `url_sniffer.py` | mitmproxy sniffer script |
| `requirements.txt` | Python dependencies |

---

## ❓ Common Problems

**Problem:** `pip` command not found  
**Fix:** Python install करते वक्त "Add to PATH" check करें, फिर VS Code restart करें

**Problem:** Firefox proxy से connect नहीं हो रहा  
**Fix:** Firefox Settings → Network → Manual Proxy → `127.0.0.1:8080` set करें

**Problem:** `mitmdump` not found  
**Fix:** `pip install mitmproxy` terminal में run करें
