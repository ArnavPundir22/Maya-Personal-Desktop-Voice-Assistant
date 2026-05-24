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
        vol_match = re.search(r'(?:set|change|adjust|put)\s+(?:the\s+)?volume\s+(?:to\s+)?(\d+)', query_clean)
        if vol_match:
            return set_volume(int(vol_match.group(1)))

        # "volume up", "increase volume", "turn up the volume", "raise volume"
        if re.search(r'(?:volume\s+up|increase\s+(?:the\s+)?volume|turn\s+up\s+(?:the\s+)?volume|raise\s+(?:the\s+)?volume|louder)', query_clean):
            current = get_volume()
            new_vol = min(100, (current if current >= 0 else 50) + 10)
            return set_volume(new_vol)

        # "volume down", "decrease volume", "turn down the volume", "lower volume", "quieter"
        if re.search(r'(?:volume\s+down|decrease\s+(?:the\s+)?volume|turn\s+down\s+(?:the\s+)?volume|lower\s+(?:the\s+)?volume|reduce\s+(?:the\s+)?volume|quieter)', query_clean):
            current = get_volume()
            new_vol = max(0, (current if current >= 0 else 50) - 10)
            return set_volume(new_vol)

        if 'mute' in query_clean and 'unmute' not in query_clean:
            return set_volume(0)
        if 'unmute' in query_clean:
            return set_volume(50)

        if re.search(r'(?:what|current|check)\s*(?:is\s+)?(?:the\s+)?volume', query_clean):
            v = get_volume()
            return f"Current volume is {v}%." if v >= 0 else "Could not read volume."

        # ── Brightness Control (flexible matching) ──
        br_match = re.search(r'(?:set|change|adjust|put)\s+(?:the\s+)?brightness\s+(?:to\s+)?(\d+)', query_clean)
        if br_match:
            return set_brightness(int(br_match.group(1)))

        if re.search(r'(?:brightness\s+up|increase\s+(?:the\s+)?brightness|turn\s+up\s+(?:the\s+)?brightness|brighter)', query_clean):
            current = get_brightness()
            new_br = min(100, (current if current >= 0 else 50) + 10)
            return set_brightness(new_br)

        if re.search(r'(?:brightness\s+down|decrease\s+(?:the\s+)?brightness|turn\s+down\s+(?:the\s+)?brightness|lower\s+(?:the\s+)?brightness|dimmer|dim)', query_clean):
            current = get_brightness()
            new_br = max(10, (current if current >= 0 else 50) - 10)
            return set_brightness(new_br)

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
