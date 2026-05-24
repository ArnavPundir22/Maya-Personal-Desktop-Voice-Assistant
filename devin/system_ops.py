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
