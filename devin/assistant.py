"""
Core Assistant logic for Maya.
Handles command parsing, routing, and conversation management.
All commands are routed through process_command().
"""
import re
import os
import datetime
import webbrowser
import wikipedia
from queue import Queue

from PyQt5.QtCore import QObject, pyqtSignal

from devin.system_ops import (
    set_volume, get_volume, set_brightness, get_brightness,
    open_application, close_application, get_running_apps,
    get_system_info, get_ip_address, control_media,
    take_screenshot, calculate, get_weather, lock_screen
)
from devin.ai_engine import AIEngine, set_api_key


def replace_number_words(text):
    """Replace spoken/written number words (zero to one hundred) with digits."""
    num_words = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
        'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
        'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40,
        'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80,
        'ninety': 90, 'hundred': 100
    }
    
    text_clean = text.lower().replace('-', ' ')
    words = text_clean.split()
    
    result = []
    i = 0
    while i < len(words):
        if words[i] in num_words:
            num_seq = []
            while i < len(words) and (words[i] in num_words or words[i] == 'and'):
                num_seq.append(words[i])
                i += 1
            if num_seq and num_seq[-1] == 'and':
                num_seq.pop()
                i -= 1
            val = 0
            if 'hundred' in num_seq:
                idx = num_seq.index('hundred')
                prefix = num_seq[idx-1] if idx > 0 else 'one'
                val += num_words.get(prefix, 1) * 100
                num_seq = num_seq[idx+1:]
            for w in num_seq:
                if w in num_words:
                    val += num_words[w]
            result.append(str(val))
        else:
            result.append(words[i])
            i += 1
    return ' '.join(result)


class MayaAssistant(QObject):
    """Core assistant that processes commands and produces responses."""

    # Signals for thread-safe GUI communication
    response_ready = pyqtSignal(str, str)   # (sender, message)
    status_changed = pyqtSignal(str)        # status text
    ai_status_changed = pyqtSignal(bool)    # AI available?

    def __init__(self):
        super().__init__()
        self.ai = AIEngine()
        self.command_queue = Queue()

    def process_command(self, text):
        """Process a user command and return a response string."""
        if not text or not text.strip():
            return "I didn't catch that. Could you repeat?"

        query = text.lower().strip()
        query_clean = re.sub(r'[^\w\s]', '', query)
        query_clean = replace_number_words(query_clean)

        # ── API Key Configuration ──
        if query_clean.startswith('set api key') or query_clean.startswith('set gemini key'):
            key = re.sub(r'^set\s+(api|gemini)\s+key\s*', '', text.strip(), flags=re.IGNORECASE).strip()
            if key:
                set_api_key(key)
                self.ai.reload()
                self.ai_status_changed.emit(self.ai.is_ai_available)
                if self.ai.is_ai_available:
                    return "✅ Gemini API key saved and connected! I'm now AI-powered. Ask me anything!"
                else:
                    return "⚠️ API key saved but couldn't connect to Gemini. Please check the key."
            return "Please provide the API key: 'set api key YOUR_KEY_HERE'"

        # ── Time & Date ──
        if any(w in query_clean for w in ['what time', 'current time', 'whats the time', 'tell me the time']):
            now = datetime.datetime.now().strftime("%I:%M %p")
            return f"The current time is {now}."

        if any(w in query_clean for w in ['what date', 'todays date', 'current date', 'what day']):
            now = datetime.datetime.now().strftime("%A, %B %d, %Y")
            return f"Today is {now}."

        # ── Volume Control (flexible matching) ──
        if any(w in query_clean for w in ['volume', 'sound', 'audio', 'speaker', 'speakers', 'quieter', 'louder']):
            # Check for relative change with a specific number, e.g., "increase volume by 20"
            by_match = re.search(r'(?:increase|up|raise|turn\s+up|louder)\s+(?:by\s+)?(\d+)', query_clean)
            if by_match:
                current = get_volume()
                return set_volume(min(100, (current if current >= 0 else 50) + int(by_match.group(1))))
                
            by_match_down = re.search(r'(?:decrease|down|lower|turn\s+down|quieter|reduce)\s+(?:by\s+)?(\d+)', query_clean)
            if by_match_down:
                current = get_volume()
                return set_volume(max(0, (current if current >= 0 else 50) - int(by_match_down.group(1))))

            # Check for absolute value setting, e.g., "set volume to 80", "volume 50"
            val_match = re.search(r'(\d+)', query_clean)
            if val_match:
                return set_volume(int(val_match.group(1)))

        # Relative change without specified number (default +/- 10%)
        if any(w in query_clean for w in ['volume up', 'increase volume', 'turn up the volume', 'raise volume', 'louder', 'turn up volume', 'make it louder', 'turn the volume up']):
            current = get_volume()
            new_vol = min(100, (current if current >= 0 else 50) + 10)
            return set_volume(new_vol)

        if any(w in query_clean for w in ['volume down', 'decrease volume', 'turn down the volume', 'lower volume', 'reduce volume', 'quieter', 'turn down volume', 'make it quieter', 'turn the volume down']):
            current = get_volume()
            new_vol = max(0, (current if current >= 0 else 50) - 10)
            return set_volume(new_vol)

        if 'mute' in query_clean and 'unmute' not in query_clean:
            return set_volume(0)
        if 'unmute' in query_clean:
            return set_volume(50)

        if re.search(r'(?:what|current|check|get)\s*(?:is\s+)?(?:the\s+)?volume', query_clean):
            v = get_volume()
            return f"Current volume is {v}%." if v >= 0 else "Could not read volume."

        # ── Brightness Control (flexible matching) ──
        if any(w in query_clean for w in ['brightness', 'screen', 'display', 'backlight', 'brighter', 'dimmer', 'dim']):
            # Check for relative change with a specific number, e.g., "increase brightness by 20"
            by_match = re.search(r'(?:increase|up|raise|turn\s+up|brighter|make\s+brighter)\s+(?:by\s+)?(\d+)', query_clean)
            if by_match:
                current = get_brightness()
                return set_brightness(min(100, (current if current >= 0 else 50) + int(by_match.group(1))))
                
            by_match_down = re.search(r'(?:decrease|down|lower|turn\s+down|dimmer|dim|reduce)\s+(?:by\s+)?(\d+)', query_clean)
            if by_match_down:
                current = get_brightness()
                return set_brightness(max(10, (current if current >= 0 else 50) - int(by_match_down.group(1))))

            # Check for absolute value setting, e.g., "set screen to 80", "brightness 50"
            val_match = re.search(r'(\d+)', query_clean)
            if val_match:
                return set_brightness(int(val_match.group(1)))

        # Relative change without specified number (default +/- 10%)
        if any(w in query_clean for w in ['brightness up', 'increase brightness', 'turn up the brightness', 'brighter', 'make screen brighter', 'turn up brightness', 'make display brighter']):
            current = get_brightness()
            new_br = min(100, (current if current >= 0 else 50) + 10)
            return set_brightness(new_br)

        if any(w in query_clean for w in ['brightness down', 'decrease brightness', 'turn down the brightness', 'dimmer', 'dim', 'turn down brightness', 'make screen dimmer', 'make display dimmer']):
            current = get_brightness()
            new_br = max(10, (current if current >= 0 else 50) - 10)
            return set_brightness(new_br)

        if re.search(r'(?:what|current|check|get)\s*(?:is\s+)?(?:the\s+)?brightness', query_clean):
            v = get_brightness()
            return f"Current brightness is {v}%." if v >= 0 else "Could not read brightness."

        # ── App Control ──
        open_match = re.search(r'(?:open|launch|start|run)\s+(.+)', query_clean)
        if open_match:
            app_name = open_match.group(1).strip()
            # Check if it's a website URL
            if any(w in app_name for w in ['google.com', 'youtube.com', '.com', '.org', '.io', '.net']):
                url = app_name if app_name.startswith('http') else f"https://{app_name}"
                webbrowser.open(url)
                return f"Opening {app_name} in your browser."
            # Named websites
            web_shortcuts = {
                'google': 'https://www.google.com',
                'youtube': 'https://www.youtube.com',
                'chatgpt': 'https://chat.openai.com',
                'chat gpt': 'https://chat.openai.com',
                'github': 'https://github.com',
                'gmail': 'https://mail.google.com',
                'reddit': 'https://www.reddit.com',
                'twitter': 'https://twitter.com',
                'x': 'https://x.com',
                'linkedin': 'https://www.linkedin.com',
                'stackoverflow': 'https://stackoverflow.com',
                'stack overflow': 'https://stackoverflow.com',
                'wikipedia': 'https://www.wikipedia.org',
                'whatsapp': 'https://web.whatsapp.com',
                'spotify': 'https://open.spotify.com',
                'netflix': 'https://www.netflix.com',
                'amazon': 'https://www.amazon.com',
            }
            if app_name in web_shortcuts:
                webbrowser.open(web_shortcuts[app_name])
                return f"Opening {app_name}."
            return open_application(app_name)

        close_match = re.search(r'(?:close|kill|stop|quit|exit)\s+(.+)', query_clean)
        if close_match:
            app_name = close_match.group(1).strip()
            if app_name in ('maya', 'yourself', 'assistant'):
                return "Goodbye! Shutting down..."
            return close_application(app_name)

        # ── Media Control ──
        if any(w in query_clean for w in ['pause music', 'play music', 'pause video', 'resume']):
            return control_media('play')
        if 'next song' in query_clean or 'next track' in query_clean or 'skip' in query_clean:
            return control_media('next')
        if 'previous song' in query_clean or 'previous track' in query_clean:
            return control_media('previous')

        # ── Web Search ──
        search_match = re.search(r'(?:search|google|look up)\s+(?:for\s+)?(.+)', query_clean)
        if search_match:
            term = search_match.group(1).strip()
            url = f"https://www.google.com/search?q={term.replace(' ', '+')}"
            webbrowser.open(url)
            return f"Searching Google for: {term}"

        yt_match = re.search(r'play\s+(.+)\s+on\s+youtube', query_clean)
        if yt_match:
            term = yt_match.group(1).strip()
            url = f"https://www.youtube.com/results?search_query={term.replace(' ', '+')}"
            webbrowser.open(url)
            return f"Searching YouTube for: {term}"

        # ── Wikipedia ──
        wiki_match = re.search(r'(?:wikipedia|wiki)\s+(.+)', query_clean)
        if wiki_match:
            topic = wiki_match.group(1).strip()
            try:
                result = wikipedia.summary(topic, sentences=2)
                return f"📚 {result}"
            except:
                return f"Could not find Wikipedia article for: {topic}"

        # ── Weather ──
        weather_match = re.search(r'weather\s*(?:in|for|at)?\s*(.*)', query_clean)
        if weather_match or 'weather' in query_clean:
            city = weather_match.group(1).strip() if weather_match else ""
            return f"🌤️ {get_weather(city)}"

        # ── System Info ──
        if any(w in query_clean for w in ['system info', 'system status', 'how is my system',
                                           'cpu usage', 'ram usage', 'disk space', 'battery']):
            info = get_system_info()
            parts = [
                f"💻 CPU: {info['cpu_percent']}% ({info['cpu_count']} cores)",
                f"🧠 RAM: {info['ram_used_gb']}/{info['ram_total_gb']} GB ({info['ram_percent']}%)",
                f"💾 Disk: {info['disk_used_gb']}/{info['disk_total_gb']} GB ({info['disk_percent']}%)",
                f"⏱️ Uptime: {info['uptime_hours']} hours",
            ]
            if info.get('battery_percent') is not None:
                plug = "🔌 Plugged in" if info['battery_plugged'] else "🔋 On battery"
                parts.append(f"🔋 Battery: {info['battery_percent']}% ({plug})")
            return "\n".join(parts)

        if any(w in query_clean for w in ['my ip', 'ip address', 'whats my ip']):
            ips = get_ip_address()
            return f"🌐 Local IP: {ips['local']}\n🌍 Public IP: {ips['public']}"

        # ── Screenshot ──
        if any(w in query_clean for w in ['screenshot', 'screen capture', 'take a screenshot', 'capture screen']):
            return f"📸 {take_screenshot()}"

        # ── Calculator ──
        calc_match = re.search(r'(?:calculate|calc|compute|solve|whats|what is)\s+(.+)', query_clean)
        if calc_match:
            expr = calc_match.group(1).strip()
            if re.search(r'[\d+\-*/^().]', expr):
                result = calculate(expr)
                if 'Could not' not in result:
                    return f"🔢 {result}"

        # ── Lock Screen ──
        if any(w in query_clean for w in ['lock screen', 'lock my computer', 'lock pc']):
            return lock_screen()

        # ── Running Apps ──
        if any(w in query_clean for w in ['running apps', 'running processes', 'active apps', 'list apps']):
            apps = get_running_apps()[:20]
            return "📋 Running applications:\n" + ", ".join(apps)

        # ── Exit ──
        if query_clean in ('exit', 'quit', 'goodbye', 'bye', 'shut down maya', 'close maya'):
            return "👋 Goodbye! Call me when you need me again."

        # ── AI Chat (catch-all) ──
        return self.ai.chat(text)
