"""
Core Assistant logic for Maya.
Handles command parsing, routing, and conversation management.
All commands are routed through process_command().
"""
import re
import os
import time
import random
import datetime
import webbrowser
import wikipedia
from queue import Queue

from PyQt5.QtCore import QObject, pyqtSignal

from devin.system_ops import (
    set_volume, get_volume, set_brightness, get_brightness,
    open_application, close_application, get_running_apps,
    get_system_info, get_ip_address, control_media,
    take_screenshot, calculate, get_weather, lock_screen,
    scrape_website_text, send_whatsapp_message, play_on_youtube,
    compose_email, set_wifi, set_bluetooth, empty_trash, find_file,
    take_webcam_photo, create_note_and_send
)
from devin.ai_engine import AIEngine, set_api_key
from devin import realtime_data as rt


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
    window_action_signal = pyqtSignal(str)  # "minimize" or "restore"

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

        # ── Weather API Key ──
        if re.search(r'set\s+weather\s+(?:api\s+)?key', query_clean):
            key = re.sub(r'^set\s+weather\s+(?:api\s+)?key\s*', '', text.strip(), flags=re.IGNORECASE).strip()
            if key:
                rt.save_api_keys(owm_api_key=key)
                return "✅ OpenWeatherMap API key saved! Detailed weather data is now enabled."
            return "Please provide the key: 'set weather key YOUR_OWM_KEY'"

        # ── News API Key ──
        if re.search(r'set\s+news\s+(?:api\s+)?key', query_clean):
            key = re.sub(r'^set\s+news\s+(?:api\s+)?key\s*', '', text.strip(), flags=re.IGNORECASE).strip()
            if key:
                rt.save_api_keys(news_api_key=key)
                return "✅ NewsAPI key saved! Full news access is now enabled."
            return "Please provide the key: 'set news key YOUR_NEWS_API_KEY'"

        # ── Telegram Config ──
        if re.search(r'set\s+telegram\s+token', query_clean):
            key = re.sub(r'^set\s+telegram\s+token\s*', '', text.strip(), flags=re.IGNORECASE).strip()
            if key:
                from devin.ai_engine import load_config, save_config
                config = load_config()
                config['telegram_token'] = key
                save_config(config)
                return "✅ Telegram Bot Token saved!"
            return "Please provide the token: 'set telegram token YOUR_TOKEN'"
            
        if re.search(r'set\s+telegram\s+chat\s+id', query_clean):
            key = re.sub(r'^set\s+telegram\s+chat\s+id\s*', '', text.strip(), flags=re.IGNORECASE).strip()
            if key:
                from devin.ai_engine import load_config, save_config
                config = load_config()
                config['telegram_chat_id'] = key
                save_config(config)
                return "✅ Telegram Chat ID saved!"
            return "Please provide the ID: 'set telegram chat id YOUR_ID'"

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

        # ── WhatsApp Message ──
        contact, message = None, None
        m1 = re.search(r'send\s+(?:a\s+)?(?:whatsapp\s+)?message\s+to\s+(.+?)\s+saying\s+(.+)', query_clean)
        m2 = re.search(r'message\s+(.+?)\s+(?:on\s+whatsapp\s+)?saying\s+(.+)', query_clean)
        m3 = re.search(r'send\s+(?:a\s+)?(.+?)(?:\s+message)?\s+to\s+(.*?)(?:\s+(?:on|using)\s+whatsapp)?$', query_clean)
        
        if m1:
            contact, message = m1.group(1).strip(), m1.group(2).strip()
        elif m2:
            contact, message = m2.group(1).strip(), m2.group(2).strip()
        elif m3:
            msg_part = m3.group(1).strip()
            if msg_part.endswith(" message"):
                msg_part = msg_part[:-8].strip()
            contact, message = m3.group(2).strip(), msg_part
            
        if contact and message and 'whatsapp' in query_clean:
            contact = re.sub(r'\s+on\s+whatsapp$', '', contact).strip()
            self.status_changed.emit("💬 Opening WhatsApp...")
            return send_whatsapp_message(contact, message)

        # ── YouTube Search & Play ──
        yt_search_match = re.search(r'search\s+(?:for\s+)?(.+?)\s+on\s+youtube', query_clean)
        if yt_search_match:
            term = yt_search_match.group(1).strip()
            url = f"https://www.youtube.com/results?search_query={term.replace(' ', '+')}"
            webbrowser.open(url)
            self.status_changed.emit(f"🔍 Searching YouTube for {term}...")
            return f"Searching YouTube for: {term}"

        yt_play_match = re.search(r'play\s+(.+)\s+on\s+youtube', query_clean)
        if yt_play_match:
            term = yt_play_match.group(1).strip()
            self.status_changed.emit(f"🎵 Playing {term} on YouTube...")
            return play_on_youtube(term)

        # ── Compound Open & Search ──
        open_search_match = re.search(r'open\s+(google|youtube|browser|website)\s+and\s+search\s+(?:for\s+)?(.+)', query_clean)
        if open_search_match:
            platform = open_search_match.group(1).strip()
            term = open_search_match.group(2).strip()
            if platform == 'youtube':
                url = f"https://www.youtube.com/results?search_query={term.replace(' ', '+')}"
                webbrowser.open(url)
                self.status_changed.emit(f"🔍 Searching YouTube for {term}...")
                return f"Searching YouTube for: {term}"
            else:
                url = f"https://www.google.com/search?q={term.replace(' ', '+')}"
                webbrowser.open(url)
                self.status_changed.emit(f"🔍 Searching Google for {term}...")
                return f"Searching Google for: {term}"

        # ── App Control ──
        open_match = re.search(r'(?:open|launch|start|run)\s+(.+)', query_clean)
        if open_match and " and " not in open_match.group(1) and " search " not in open_match.group(1):
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
                'chatgpt': 'https://chatgpt.com',
                'chat gpt': 'https://chatgpt.com',
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
                'whatsapp web': 'https://web.whatsapp.com',
                'whatsapp on browser': 'https://web.whatsapp.com',
                'whatsapp desktop': 'https://web.whatsapp.com',
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


        # ── Wikipedia ──
        wiki_match = re.search(r'(?:wikipedia|wiki)\s+(.+)', query_clean)
        if wiki_match:
            topic = wiki_match.group(1).strip()
            try:
                result = wikipedia.summary(topic, sentences=2)
                return f"📚 {result}"
            except:
                return f"Could not find Wikipedia article for: {topic}"

        # ── Weather (enhanced with real-time module) ──
        weather_match = re.search(r'weather\s*(?:in|for|at)?\s*(.*)', query_clean)
        if weather_match or 'weather' in query_clean:
            city = weather_match.group(1).strip() if weather_match else ""
            # Multi-day forecast?
            day_match = re.search(r'(\d+)[- ]day|next\s+(\d+)\s+day', query_clean)
            if day_match or any(w in query_clean for w in ['forecast', 'week', 'tomorrow']):
                days = int(day_match.group(1) or day_match.group(2)) if day_match else 3
                days = min(days, 7)
                return rt.get_weather_forecast(city, days)
            return rt.get_weather_detailed(city)

        # ── News ──
        news_match = re.search(
            r'(?:latest|top|recent|current|today[s\']?)?\s*news\s*(?:about|on|for)?\s*(.*)',
            query_clean
        )
        if news_match or any(w in query_clean for w in ['headlines', 'whats happening', 'current events']):
            topic = ""
            if news_match:
                topic = news_match.group(1).strip()
            # Count requested?
            count_match = re.search(r'(\d+)\s+news|news\s+(\d+)', query_clean)
            count = int(count_match.group(1) or count_match.group(2)) if count_match else 5
            count = min(count, 10)
            return rt.get_news(topic, count)

        # ── Cryptocurrency ──
        crypto_kw = ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'dogecoin', 'doge',
                     'solana', 'sol', 'binance', 'bnb', 'ripple', 'xrp', 'cardano', 'ada',
                     'litecoin', 'ltc', 'polkadot', 'polygon', 'matic', 'avalanche', 'avax',
                     'chainlink', 'link', 'uniswap', 'uni']
        query_words = set(query_clean.split())
        if any(w in query_words for w in crypto_kw):
            # Market overview?
            if any(w in query_words for w in ['market', 'top', 'overview', 'all']):
                return rt.get_crypto_market_overview(5)
            # Specific coin
            for kw in crypto_kw:
                if kw in query_words:
                    return rt.get_crypto_price(kw)
            return rt.get_crypto_market_overview(5)

        # ── Stocks ──
        stock_match = re.search(
            r'(?:stock|share|price|quote)\s+(?:of\s+|for\s+)?([A-Za-z]{1,5})',
            query_clean
        )
        if not stock_match:
            # "TSLA stock", "AAPL price"
            stock_match = re.search(
                r'\b([A-Z]{2,5})\b\s+(?:stock|share|price|quote)',
                text  # use original case
            )
        if stock_match:
            ticker = stock_match.group(1).upper()
            return rt.get_stock_price(ticker)

        # ── Sunrise / Sunset ──
        if any(w in query_clean for w in ['sunrise', 'sunset', 'dawn', 'dusk', 'golden hour']):
            sun_match = re.search(r'(?:sunrise|sunset|dawn|dusk)\s*(?:in|for|at)?\s*(.*)', query_clean)
            city = sun_match.group(1).strip() if sun_match and sun_match.group(1).strip() else ""
            return rt.get_sun_times(city)

        # ── Holidays ──
        if any(w in query_clean for w in ['holiday', 'holidays', 'public holiday', 'national holiday']):
            country_match = re.search(r'(?:holiday|holidays)\s+(?:in|for)\s+([a-z]{2,3})', query_clean)
            country = country_match.group(1).upper() if country_match else "IN"
            return rt.get_upcoming_holidays(country)

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

        # ── Screenshot & Camera ──
        if any(w in query_clean for w in ['screenshot', 'screen capture', 'take a screenshot', 'capture screen']):
            return f"📸 {take_screenshot()}"
            
        if any(w in query_clean for w in ['take a photo', 'take a picture', 'take a selfie', 'capture photo']):
            self.status_changed.emit("📷 Taking a photo...")
            return f"📷 {take_webcam_photo()}"

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

        # ── Network & Connectivity ──
        if re.search(r'(?:turn|switch)\s+on\s+(?:wifi|wi-fi)', query_clean):
            return set_wifi('on')
        if re.search(r'(?:turn|switch)\s+off\s+(?:wifi|wi-fi)', query_clean):
            return set_wifi('off')
        if re.search(r'(?:turn|switch)\s+on\s+bluetooth', query_clean):
            return set_bluetooth('on')
        if re.search(r'(?:turn|switch)\s+off\s+bluetooth', query_clean):
            return set_bluetooth('off')

        # ── File Operations ──
        if any(w in query_clean for w in ['empty trash', 'empty the trash', 'clear trash', 'empty bin', 'clear recycle bin']):
            return empty_trash()
            
        find_match = re.search(r'(?:find|search\s+for|locate)\s+(?:the\s+)?(?:file\s+)?(.+)', query_clean)
        if find_match and not any(w in query_clean for w in ['youtube', 'google', 'online', 'web']):
            # Avoid matching web searches
            if ' on ' not in find_match.group(1):
                filename = find_match.group(1).strip()
                self.status_changed.emit(f"🔍 Searching files for '{filename}'...")
                return find_file(filename)

        # ── Running Apps ──
        if any(w in query_clean for w in ['running apps', 'running processes', 'active apps', 'list apps']):
            apps = get_running_apps()[:20]
            return "📋 Running applications:\n" + ", ".join(apps)

        # ── Real-Time Help ──
        if any(w in query_clean for w in ['what can you do', 'help', 'commands', 'features']):
            return (
                "Here's what I can do in real-time:\n"
                "🌦️ Weather: 'weather in Delhi', 'forecast for London'\n"
                "📰 News: 'latest news', 'news about AI', 'top 5 headlines'\n"
                "💰 Crypto: 'bitcoin price', 'ethereum', 'top 5 crypto'\n"
                "📊 Stocks: 'TSLA stock', 'AAPL price', 'price of GOOGL'\n"
                "☀️ Sun times: 'sunrise today', 'sunset in Mumbai'\n"
                "🎉 Holidays: 'holidays in US', 'upcoming holidays'\n"
                "Plus volume, brightness, apps, screenshots, system info & AI chat!"
            )

        # ── Interactive Presets (Fun & Conversational) ──
        if query_clean in ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening', 'howdy']:
            hour = datetime.datetime.now().hour
            greeting = "Good morning!" if hour < 12 else "Good afternoon!" if hour < 17 else "Good evening!"
            return f"{greeting} How can I assist you today?"

        if any(w in query_clean for w in ['how are you', 'how are you doing']):
            return random.choice([
                "I'm fully operational and ready to help! How are you?",
                "Running smoothly on all cylinders! What's on your mind?",
                "I'm doing great, thanks for asking! What can I do for you today?"
            ])

        if any(w in query_clean for w in ['who are you', 'what are you']):
            return "I am your personal AI desktop assistant. I can help you with your system, web searches, and more!"

        if any(w in query_clean for w in ['who made you', 'who created you']):
            return "I was created by a very talented developer to be your ultimate desktop companion."

        if any(w in query_clean for w in ['tell me a joke', 'make me laugh', 'say a joke']):
            jokes = [
                "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
                "There are only 10 types of people: those who understand binary and those who don't.",
                "A SQL query walks into a bar, sees two tables and asks... 'Can I JOIN you?'",
                "Why was the JavaScript developer sad? He didn't Node how to Express himself! 😄",
                "What's a programmer's favorite hangout? Foo Bar! 🍺"
            ]
            return random.choice(jokes)

        if any(w in query_clean for w in ['flip a coin', 'toss a coin']):
            result = random.choice(['Heads', 'Tails'])
            return f"🪙 I flipped a coin... It's {result}!"

        if any(w in query_clean for w in ['roll a dice', 'roll a die']):
            result = random.randint(1, 6)
            return f"🎲 I rolled a dice and got a {result}."

        if any(w in query_clean for w in ['random number', 'give me a random number']):
            result = random.randint(1, 100)
            return f"🔢 Here's a random number between 1 and 100: {result}."

        if any(w in query_clean for w in ['sing a song', 'can you sing']):
            return "🎵 Daisy, Daisy, give me your answer do... 🎶 Just kidding, I'll stick to assisting!"

        if any(w in query_clean for w in ['meaning of life', 'what is the meaning of life']):
            return "According to my calculations, it's 42. But spending time with friends and family is a close second!"

        # ── Standby ──
        if query_clean in ('wait', 'hold', 'standby', 'go to standby', 'pause', 'stop listening', 'shut up'):
            return "Going into standby. Say 'listen' to wake me up."

        # ── Wake ──
        if query_clean in ('listen', 'wake up', 'awake', 'start listening', 'maya listen'):
            return "I'm awake! What do you need?"

        # ── Exit ──
        if query_clean in ('exit', 'quit', 'goodbye', 'bye', 'shut down maya', 'close maya', 'shut down', 'close'):
            return "👋 Goodbye! Call me when you need me again."

        # ── AI Intent Parsing (Smart Fallback) ──
        self.status_changed.emit("🧠 Analyzing complex command...")
        intent = self.ai.extract_action(text)
        if intent and intent.get('action') and intent.get('action') != 'chat':
            action = intent.get('action')
            if action == 'open_app':
                target = intent.get('target', '')
                search = intent.get('search', '')
                if search and 'youtube' in target.lower():
                    url = f"https://www.youtube.com/results?search_query={search.replace(' ', '+')}"
                    webbrowser.open(url)
                    return f"Opening YouTube and searching for {search}"
                elif search:
                    url = f"https://www.google.com/search?q={search.replace(' ', '+')}"
                    webbrowser.open(url)
                    return f"Opening {target} and searching for {search}"
                else:
                    return open_application(target)
            elif action == 'close_app':
                return close_application(intent.get('target', ''))
            elif action == 'search_youtube':
                q = intent.get('query', '')
                url = f"https://www.youtube.com/results?search_query={q.replace(' ', '+')}"
                webbrowser.open(url)
                return f"Searching YouTube for {q}"
            elif action == 'search_google':
                q = intent.get('query', '')
                url = f"https://www.google.com/search?q={q.replace(' ', '+')}"
                webbrowser.open(url)
                return f"Searching Google for {q}"
            elif action == 'play_youtube':
                return play_on_youtube(intent.get('query', ''))
            elif action == 'weather':
                return get_weather(intent.get('location', ''))
            elif action == 'set_volume':
                return set_volume(intent.get('level', 50))
            elif action == 'set_brightness':
                return set_brightness(intent.get('level', 50))
            elif action == 'media_control':
                return control_media(intent.get('command', 'play'))
            elif action == 'take_screenshot':
                return f"📸 {take_screenshot()}"
            elif action == 'system_info':
                info = get_system_info()
                return f"💻 System Info: CPU {info['cpu_percent']}%, RAM {info['ram_percent']}%, Battery {info.get('battery_percent', 'N/A')}%"
            elif action == 'lock_screen':
                return lock_screen()
            elif action == 'send_whatsapp':
                self.status_changed.emit("💬 Opening WhatsApp...")
                return send_whatsapp_message(intent.get('contact', ''), intent.get('message', ''))
            elif action == 'send_email':
                self.status_changed.emit("📧 Opening email client...")
                return compose_email(intent.get('to', ''), intent.get('subject', ''), intent.get('body', ''))
            elif action == 'math':
                return f"🔢 {calculate(intent.get('expression', ''))}"
            elif action == 'set_wifi':
                return set_wifi(intent.get('state', 'on'))
            elif action == 'set_bluetooth':
                return set_bluetooth(intent.get('state', 'on'))
            elif action == 'empty_trash':
                return empty_trash()
            elif action == 'find_file':
                self.status_changed.emit(f"🔍 Searching files for '{intent.get('filename', '')}'...")
                return find_file(intent.get('filename', ''))
            elif action == 'take_photo':
                self.status_changed.emit("📷 Taking a photo...")
                return f"📷 {take_webcam_photo()}"
            elif action == 'create_note':
                self.status_changed.emit("📝 Creating note...")
                return create_note_and_send(intent.get('message', ''), intent.get('filename', 'note.txt'), intent.get('platform', ''))
        # ── AI Chat (catch-all) ──
        urls = re.findall(r'(https?://[^\s]+)', text)
        context_block = ""
        if urls:
            self.status_changed.emit("🔍 Scraping website content...")
            scraped_contexts = []
            for url in urls:
                # Remove trailing punctuation from URL if regex grabbed it
                clean_url = url.rstrip('.,;()[]{}')
                content = scrape_website_text(clean_url)
                if not content.startswith("Error"):
                    scraped_contexts.append(f"Source URL: {clean_url}\nContent:\n{content}")
            if scraped_contexts:
                context_block = "\n\n".join(scraped_contexts)
                self.status_changed.emit("💬 Analyzing content with Gemini...")
            else:
                self.status_changed.emit("⚠️ Failed to scrape link(s)")

        return self.ai.chat(text, context=context_block if context_block else None)
