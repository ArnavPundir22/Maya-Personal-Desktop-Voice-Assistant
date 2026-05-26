"""
System operations for Maya AI Assistant (Ubuntu/Linux).
Handles volume, brightness, apps, system info, media, screenshots, etc.
"""
import os
import re
import ast
import math
import shutil
import subprocess
import psutil
import datetime
import urllib.parse
import time
import webbrowser
import pyautogui

# ── Volume Control ──────────────────────────────────────────────
try:
    import pulsectl
    HAS_PULSECTL = True
except ImportError:
    HAS_PULSECTL = False

def set_volume(level):
    """Set system volume (0-100). Returns status message."""
    level = max(0, min(100, int(level)))
    try:
        if HAS_PULSECTL:
            with pulsectl.Pulse('devin') as pulse:
                for sink in pulse.sink_list():
                    pulse.volume_set_all_chans(sink, level / 100.0)
        else:
            subprocess.run(['amixer', 'set', 'Master', f'{level}%'],
                           capture_output=True, timeout=5)
        return f"Volume set to {level}%."
    except Exception as e:
        return f"Failed to set volume: {e}"

def get_volume():
    """Get current system volume percentage."""
    try:
        if HAS_PULSECTL:
            with pulsectl.Pulse('devin') as pulse:
                sinks = pulse.sink_list()
                if sinks:
                    vol = pulse.volume_get_all_chans(sinks[0])
                    return int(vol * 100)
        else:
            out = subprocess.check_output(['amixer', 'get', 'Master'], timeout=5).decode()
            m = re.search(r'\[(\d+)%\]', out)
            if m:
                return int(m.group(1))
    except:
        pass
    return -1

# ── Brightness Control ──────────────────────────────────────────
# GNOME D-Bus is the most reliable on Ubuntu with GNOME desktop.
# xrandr software brightness is the fallback.

def _get_xrandr_output():
    """Get the primary display output name from xrandr."""
    try:
        out = subprocess.check_output(['xrandr', '--current'], timeout=5).decode()
        for line in out.split('\n'):
            if ' connected' in line:
                return line.split()[0]
    except:
        pass
    return None

def set_brightness(level):
    """Set screen brightness (0-100). Returns status message."""
    level = max(1, min(100, int(level)))

    # Method 1: GNOME Settings Daemon via D-Bus (real hardware backlight)
    try:
        result = subprocess.run(
            ['gdbus', 'call', '--session',
             '--dest', 'org.gnome.SettingsDaemon.Power',
             '--object-path', '/org/gnome/SettingsDaemon/Power',
             '--method', 'org.freedesktop.DBus.Properties.Set',
             'org.gnome.SettingsDaemon.Power.Screen', 'Brightness',
             f'<int32 {level}>'],
            capture_output=True, timeout=5, text=True
        )
        if result.returncode == 0:
            return f"Brightness set to {level}%."
    except:
        pass

    # Method 2: xrandr software brightness
    monitor = _get_xrandr_output()
    if monitor:
        try:
            subprocess.run(
                ['xrandr', '--output', monitor, '--brightness', str(level / 100.0)],
                timeout=5, capture_output=True
            )
            return f"Brightness set to {level}% (software)."
        except:
            pass

    return "Failed to set brightness."

def get_brightness():
    """Get current screen brightness (0-100)."""
    # Method 1: GNOME D-Bus
    try:
        result = subprocess.run(
            ['gdbus', 'call', '--session',
             '--dest', 'org.gnome.SettingsDaemon.Power',
             '--object-path', '/org/gnome/SettingsDaemon/Power',
             '--method', 'org.freedesktop.DBus.Properties.Get',
             'org.gnome.SettingsDaemon.Power.Screen', 'Brightness'],
            capture_output=True, timeout=5, text=True
        )
        if result.returncode == 0:
            m = re.search(r'<(\d+)>', result.stdout)
            if m:
                return int(m.group(1))
    except:
        pass

    # Method 2: sysfs backlight
    try:
        for name in os.listdir('/sys/class/backlight/'):
            bp = f'/sys/class/backlight/{name}/brightness'
            mp = f'/sys/class/backlight/{name}/max_brightness'
            if os.path.exists(bp) and os.path.exists(mp):
                with open(bp) as f:
                    current = int(f.read().strip())
                with open(mp) as f:
                    maximum = int(f.read().strip())
                if maximum > 0:
                    return int(current * 100 / maximum)
    except:
        pass

    return -1

# ── Application Management ──────────────────────────────────────
APP_MAP = {
    'browser': ['firefox', 'google-chrome', 'chromium-browser', 'brave-browser', 'microsoft-edge'],
    'firefox': ['firefox'],
    'chrome': ['google-chrome', 'chromium-browser'],
    'file manager': ['nautilus', 'thunar', 'nemo', 'dolphin', 'pcmanfm'],
    'files': ['nautilus', 'thunar', 'nemo', 'dolphin', 'pcmanfm'],
    'terminal': ['gnome-terminal', 'xfce4-terminal', 'konsole', 'xterm', 'tilix'],
    'text editor': ['gedit', 'xed', 'mousepad', 'kate', 'pluma', 'code'],
    'notepad': ['gedit', 'xed', 'mousepad', 'kate', 'pluma'],
    'calculator': ['gnome-calculator', 'galculator', 'kcalc', 'qalculate-gtk'],
    'settings': ['gnome-control-center', 'xfce4-settings-manager'],
    'music': ['rhythmbox', 'spotify', 'vlc', 'audacious'],
    'video': ['vlc', 'totem', 'mpv', 'celluloid'],
    'code': ['code', 'codium', 'sublime_text', 'geany'],
    'vscode': ['code'],
    'vs code': ['code'],
    'camera': ['cheese', 'snapshot', 'gnome-camera', 'kamoso'],
    'photos': ['eog', 'gthumb', 'shotwell', 'gnome-photos'],
    'calendar': ['gnome-calendar'],
    'system monitor': ['gnome-system-monitor', 'htop', 'bashtop'],
}

def open_application(name):
    """Open an application by name. Returns status message."""
    name_lower = name.lower().strip()
    candidates = APP_MAP.get(name_lower, [name_lower])
    for app in candidates:
        app_path = shutil.which(app)
        if app_path:
            try:
                subprocess.Popen([app_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Opened {app}."
            except:
                continue
    
    # Fallback to .desktop files
    desktop_dirs = ['/usr/share/applications', os.path.expanduser('~/.local/share/applications'), '/var/lib/snapd/desktop/applications']
    for d in desktop_dirs:
        if not os.path.exists(d):
            continue
        try:
            for f in os.listdir(d):
                if f.endswith('.desktop') and name_lower in f.lower():
                    subprocess.Popen(['gtk-launch', f], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"Opened {name}."
        except:
            pass

    return f"Could not find application: {name}."

def close_application(name):
    """Close an application by name. Returns status message."""
    name_lower = name.lower().strip()
    if name_lower.endswith('.exe'):
        name_lower = name_lower[:-4]
    candidates = APP_MAP.get(name_lower, [name_lower])
    closed = False
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            pname = proc.info['name'].lower()
            if any(c in pname for c in candidates) or name_lower in pname:
                proc.terminate()
                closed = True
        except:
            pass
    return f"{name} has been closed." if closed else f"No running instance of {name} found."

def get_running_apps():
    """Get list of user-visible running applications."""
    apps = set()
    for proc in psutil.process_iter(['name', 'username']):
        try:
            if proc.info['username'] == os.getenv('USER'):
                apps.add(proc.info['name'])
        except:
            pass
    return sorted(apps)

# ── System Information ──────────────────────────────────────────
def get_system_info():
    """Get comprehensive system information."""
    info = {}
    info['cpu_percent'] = psutil.cpu_percent(interval=0.5)
    info['cpu_count'] = psutil.cpu_count()
    mem = psutil.virtual_memory()
    info['ram_total_gb'] = round(mem.total / (1024**3), 1)
    info['ram_used_gb'] = round(mem.used / (1024**3), 1)
    info['ram_percent'] = mem.percent
    disk = psutil.disk_usage('/')
    info['disk_total_gb'] = round(disk.total / (1024**3), 1)
    info['disk_used_gb'] = round(disk.used / (1024**3), 1)
    info['disk_percent'] = disk.percent
    try:
        battery = psutil.sensors_battery()
        if battery:
            info['battery_percent'] = battery.percent
            info['battery_plugged'] = battery.power_plugged
        else:
            info['battery_percent'] = None
    except:
        info['battery_percent'] = None
    info['uptime_hours'] = round((datetime.datetime.now().timestamp() - psutil.boot_time()) / 3600, 1)
    return info

def get_ip_address():
    """Get local and public IP addresses."""
    result = {}
    try:
        out = subprocess.check_output(['hostname', '-I'], timeout=5).decode().strip()
        result['local'] = out.split()[0] if out else 'Unknown'
    except:
        result['local'] = 'Unknown'
    try:
        out = subprocess.check_output(['curl', '-s', 'ifconfig.me'], timeout=5).decode().strip()
        result['public'] = out
    except:
        result['public'] = 'Unknown'
    return result

# ── Media Control ───────────────────────────────────────────────
def control_media(action):
    """Control media playback. Actions: play, pause, next, previous, volume_up, volume_down."""
    try:
        # Try playerctl first (works with most Linux media players)
        if shutil.which('playerctl'):
            cmd_map = {
                'play': 'play-pause', 'pause': 'play-pause', 'toggle': 'play-pause',
                'next': 'next', 'previous': 'previous', 'prev': 'previous',
                'stop': 'stop',
            }
            if action in cmd_map:
                subprocess.run(['playerctl', cmd_map[action]], timeout=5, capture_output=True)
                return f"Media: {action}"
            elif action == 'volume_up':
                subprocess.run(['playerctl', 'volume', '0.1+'], timeout=5, capture_output=True)
                return "Volume increased."
            elif action == 'volume_down':
                subprocess.run(['playerctl', 'volume', '0.1-'], timeout=5, capture_output=True)
                return "Volume decreased."
    except:
        pass
    # Fallback: xdotool key simulation
    try:
        key_map = {
            'play': 'XF86AudioPlay', 'pause': 'XF86AudioPlay', 'toggle': 'XF86AudioPlay',
            'next': 'XF86AudioNext', 'previous': 'XF86AudioPrev', 'prev': 'XF86AudioPrev',
            'volume_up': 'XF86AudioRaiseVolume', 'volume_down': 'XF86AudioLowerVolume',
        }
        if action in key_map and shutil.which('xdotool'):
            subprocess.run(['xdotool', 'key', key_map[action]], timeout=5, capture_output=True)
            return f"Media: {action}"
    except:
        pass
    return f"Could not control media: {action}"

# ── Screenshot ──────────────────────────────────────────────────
def take_screenshot(save_path=None):
    """Take a screenshot. Returns the file path."""
    if not save_path:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        save_path = os.path.expanduser(f'~/Pictures/screenshot_{ts}.png')
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    tools = [
        (['gnome-screenshot', '-f', save_path], 'gnome-screenshot'),
        (['scrot', save_path], 'scrot'),
        (['import', '-window', 'root', save_path], 'import'),
    ]
    for cmd, name in tools:
        if shutil.which(name):
            try:
                subprocess.run(cmd, timeout=10, capture_output=True)
                if os.path.exists(save_path):
                    return f"Screenshot saved to {save_path}"
            except:
                continue
    return "Could not take screenshot. Install scrot or gnome-screenshot."

# ── Calculator ──────────────────────────────────────────────────
SAFE_MATH_NAMES = {
    'abs': abs, 'round': round, 'min': min, 'max': max,
    'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
    'sqrt': math.sqrt, 'log': math.log, 'log10': math.log10,
    'pi': math.pi, 'e': math.e, 'pow': pow,
}

def calculate(expression):
    """Safely evaluate a math expression."""
    try:
        expr = expression.strip()
        expr = expr.replace('^', '**').replace('×', '*').replace('÷', '/')
        code = compile(expr, '<calc>', 'eval')
        for name in code.co_names:
            if name not in SAFE_MATH_NAMES:
                return f"Unknown function: {name}"
        result = eval(code, {"__builtins__": {}}, SAFE_MATH_NAMES)
        if isinstance(result, float) and result == int(result):
            result = int(result)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Could not calculate: {e}"

# ── Weather ─────────────────────────────────────────────────────
def get_weather(city=""):
    """Get weather using wttr.in (no API key needed)."""
    try:
        import requests
        city = city.strip() or ""
        url = f"https://wttr.in/{city}?format=%l:+%C,+%t,+Humidity:+%h,+Wind:+%w"
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'curl'})
        if resp.status_code == 200:
            return resp.text.strip()
    except:
        pass
    return "Could not fetch weather. Check your internet connection."

# ── Screen Lock / Power ────────────────────────────────────────
def lock_screen():
    """Lock the screen."""
    cmds = [
        ['loginctl', 'lock-session'],
        ['gnome-screensaver-command', '-l'],
        ['xdg-screensaver', 'lock'],
    ]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, timeout=5)
                return "Screen locked."
            except:
                continue
    return "Could not lock screen."

# ── Web Scraping ────────────────────────────────────────────────
def scrape_website_text(url: str) -> str:
    """Fetch and scrape clean text content from a website URL using requests & BeautifulSoup."""
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, timeout=12, headers=headers)
        if resp.status_code != 200:
            return f"Error: Received HTTP status code {resp.status_code} from the website."
            
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        # Strip script, style, header, footer, nav elements
        for element in soup(["script", "style", "nav", "footer", "header", "head", "aside"]):
            element.decompose()
            
        # Get clean plain text
        text = soup.get_text(separator=' ')
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Truncate to avoid overloading context limit
        if len(clean_text) > 8000:
            clean_text = clean_text[:8000] + "... [Content Truncated]"
            
        return clean_text.strip()
    except Exception as e:
        return f"Error scraping website: {e}"

# ── WhatsApp ────────────────────────────────────────────────────
def send_whatsapp_message(contact: str, message: str) -> str:
    """Open WhatsApp Web (Automated messaging disabled due to Wayland restrictions)."""
    webbrowser.open("https://web.whatsapp.com/")
    return "Opened WhatsApp Web."

# ── Email ───────────────────────────────────────────────────────
def compose_email(to: str, subject: str, body: str) -> str:
    """Open default mail client or webmail with pre-filled fields."""
    to_safe = urllib.parse.quote(to)
    sub_safe = urllib.parse.quote(subject)
    body_safe = urllib.parse.quote(body)
    mailto_url = f"mailto:{to_safe}?subject={sub_safe}&body={body_safe}"
    webbrowser.open(mailto_url)
    return f"Opened email composer for {to}."

# ── YouTube ─────────────────────────────────────────────────────
def play_on_youtube(query: str) -> str:
    """Search YouTube and play the first video result."""
    try:
        import urllib.request
        
        query_safe = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={query_safe}"
        html = urllib.request.urlopen(url)
        video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
        
        if video_ids:
            video_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
            webbrowser.open(video_url)
            return f"Playing {query} on YouTube."
        else:
            # Fallback to search if no video ID found
            webbrowser.open(url)
            return f"Searching YouTube for {query}."
    except Exception as e:
        return f"Could not play on YouTube: {e}"

# ── Network & Connectivity ──────────────────────────────────────
def set_wifi(state: str) -> str:
    """Turn Wi-Fi on or off (state: 'on' or 'off')."""
    state = state.lower().strip()
    if state not in ['on', 'off']:
        return "Invalid Wi-Fi state. Use 'on' or 'off'."
    try:
        subprocess.run(['nmcli', 'radio', 'wifi', state], timeout=5)
        return f"Wi-Fi turned {state}."
    except Exception as e:
        return f"Could not change Wi-Fi state: {e}"

def set_bluetooth(state: str) -> str:
    """Turn Bluetooth on or off (state: 'on' or 'off')."""
    state = state.lower().strip()
    if state not in ['on', 'off']:
        return "Invalid Bluetooth state. Use 'on' or 'off'."
    try:
        action = 'unblock' if state == 'on' else 'block'
        subprocess.run(['rfkill', action, 'bluetooth'], timeout=5)
        return f"Bluetooth turned {state}."
    except Exception as e:
        return f"Could not change Bluetooth state: {e}"

# ── File Operations ─────────────────────────────────────────────
def empty_trash() -> str:
    """Empty the system trash."""
    try:
        if shutil.which('trash-empty'):
            subprocess.run(['trash-empty'], timeout=5)
            return "Trash emptied."
        else:
            trash_dir = os.path.expanduser("~/.local/share/Trash")
            if os.path.exists(trash_dir):
                shutil.rmtree(os.path.join(trash_dir, "files"), ignore_errors=True)
                shutil.rmtree(os.path.join(trash_dir, "info"), ignore_errors=True)
                os.makedirs(os.path.join(trash_dir, "files"), exist_ok=True)
                os.makedirs(os.path.join(trash_dir, "info"), exist_ok=True)
                return "Trash emptied."
    except Exception as e:
        return f"Could not empty trash: {e}"

def find_file(filename: str) -> str:
    """Find a file in the user's common home directories."""
    home_dir = os.path.expanduser("~")
    search_dirs = ['Documents', 'Downloads', 'Pictures', 'Desktop', 'Music', 'Videos']
    
    found_paths = []
    for d in search_dirs:
        dir_path = os.path.join(home_dir, d)
        if not os.path.exists(dir_path):
            continue
        # Only go 3 levels deep to avoid hanging
        for root, dirs, files in os.walk(dir_path):
            depth = root[len(dir_path):].count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
            for file in files:
                if filename.lower() in file.lower():
                    found_paths.append(os.path.join(root, file))
                    if len(found_paths) >= 5:
                        break
            if len(found_paths) >= 5:
                break
        if len(found_paths) >= 5:
            break
            
    if not found_paths:
        return f"Could not find any file matching '{filename}' in common folders."
        
    res = f"Found {len(found_paths)} matches for '{filename}':\n"
    for p in found_paths:
        res += f"- {p}\n"
    return res.strip()

# ── Camera / Webcam ─────────────────────────────────────────────
def take_webcam_photo(save_path=None) -> str:
    """Take a photo using the webcam."""
    if not save_path:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        save_path = os.path.expanduser(f'~/Pictures/webcam_{ts}.jpg')
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    # Check if a video device exists
    if not os.path.exists('/dev/video0'):
        return "Error: No webcam detected (/dev/video0 not found)."
        
    tools = [
        # ffmpeg: delay slightly to let the camera adjust exposure
        (['ffmpeg', '-y', '-f', 'video4linux2', '-i', '/dev/video0', '-vframes', '1', save_path], 'ffmpeg'),
        (['fswebcam', '-r', '1280x720', '--no-banner', save_path], 'fswebcam'),
        (['streamer', '-f', 'jpeg', '-o', save_path], 'streamer')
    ]
    
    for cmd, name in tools:
        if shutil.which(name):
            try:
                subprocess.run(cmd, timeout=10, capture_output=True)
                if os.path.exists(save_path):
                    return f"Webcam photo saved to {save_path}"
            except Exception:
                continue
                
    return "Could not take photo. Please install ffmpeg or fswebcam."

# ── Notes & Telegram Integration ────────────────────────────────
def create_note_and_send(message: str, filename: str, platform: str) -> str:
    """Create a text file, open it in an editor, and send it via Telegram/Email."""
    if not filename.endswith('.txt'):
        filename += '.txt'
    filepath = os.path.expanduser(f"~/Documents/{filename}")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # 1. Write the file
    with open(filepath, 'w') as f:
        f.write(message)
        
    # 2. Open in default text editor
    try:
        subprocess.Popen(['xdg-open', filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass
        
    # 3. Send
    platform = platform.lower() if platform else ""
    if 'telegram' in platform:
        config_path = os.path.expanduser("~/.config/maya/config.json")
        try:
            import json
            import requests
            with open(config_path) as f:
                config = json.load(f)
            token = config.get('telegram_token')
            chat_id = config.get('telegram_chat_id')
            
            if not token or not chat_id:
                return f"File saved as {filename} and opened. To send via Telegram, please say 'set telegram token YOUR_TOKEN' and 'set telegram chat id YOUR_ID'."
                
            url = f"https://api.telegram.org/bot{token}/sendDocument"
            with open(filepath, 'rb') as doc:
                resp = requests.post(url, data={'chat_id': chat_id, 'caption': 'Here is your note from Maya.'}, files={'document': doc})
            if resp.status_code == 200:
                return f"File saved as {filename}, opened in editor, and sent via Telegram! 🚀"
            else:
                return f"File saved, but Telegram failed: {resp.text}"
        except Exception as e:
            return f"File saved as {filename}, but Telegram send failed: {e}"
            
    elif 'mail' in platform or 'email' in platform:
        import urllib.parse
        import webbrowser
        sub_safe = urllib.parse.quote(f"Note: {filename}")
        body_safe = urllib.parse.quote(f"Please find the message below:\n\n{message}")
        mailto_url = f"mailto:?subject={sub_safe}&body={body_safe}"
        webbrowser.open(mailto_url)
        return f"File saved as {filename} and opened. Email draft created. 📧"
        
    return f"File saved as {filename} and opened in your text editor. 📝"

