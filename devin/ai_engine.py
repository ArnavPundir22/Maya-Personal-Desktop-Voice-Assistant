"""
AI Engine for Maya Assistant.
Integrates with Google Gemini (via google-genai SDK) for intelligent responses.
Falls back to a smart rule-based engine if no API key is configured.
Real-time weather/news context is injected into every Gemini request.
"""
import os
import json
import datetime
import random
import time
import threading

# ── Gemini Setup (google-genai SDK) ─────────────────────────────
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

CONFIG_DIR = os.path.expanduser("~/.config/maya")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

SYSTEM_PROMPT = """You are {ai_name}, a friendly and intelligent AI desktop assistant running on Ubuntu Linux.
You are helpful, witty, and concise. Keep responses under 3 sentences unless the user asks for detail.
You can help with general knowledge, coding, math, science, writing, and casual conversation.
If asked about system tasks (volume, brightness, apps), note that you handle those through system commands.
Current date/time: {datetime}
Be warm and personable. Address the user respectfully.

--- LIVE REAL-TIME DATA (use this to answer questions about current events, weather, news) ---
{live_context}
--- END LIVE DATA ---"""

# Models to try in order — newer/lite models often have separate quotas
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
]


def load_config():
    """Load config from file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}


def load_ai_name() -> str:
    """Return the configured AI name (defaults to 'Maya')."""
    return load_config().get("ai_name", "Maya")

def save_config(config):
    """Save config to file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def get_api_key():
    """Get Gemini API key from config or environment."""
    key = os.environ.get('GEMINI_API_KEY', '')
    if not key:
        config = load_config()
        key = config.get('gemini_api_key', '')
    return key

def set_api_key(key):
    """Save Gemini API key to config."""
    config = load_config()
    config['gemini_api_key'] = key
    save_config(config)


class AIEngine:
    """AI conversation engine with Gemini integration and smart fallback."""

    def __init__(self):
        self.client = None
        self.active_model = None
        self.history = []
        self._live_context = ""
        self._init_gemini()
        # Warm-up live context in background so it's ready quickly
        threading.Thread(target=self._refresh_live_context, daemon=True).start()

    def _refresh_live_context(self):
        """Refresh real-time weather/news context (called in background thread)."""
        try:
            from devin.realtime_data import get_live_context_snippet
            self._live_context = get_live_context_snippet()
        except Exception as e:
            self._live_context = ""

    def _init_gemini(self):
        """Initialize Gemini client if available and configured."""
        if not HAS_GEMINI:
            return
        api_key = get_api_key()
        if not api_key:
            return
        try:
            self.client = genai.Client(api_key=api_key)
            # Find a working model
            for model_name in GEMINI_MODELS:
                try:
                    test_resp = self.client.models.generate_content(
                        model=model_name,
                        contents="Say hi in 3 words",
                        config=types.GenerateContentConfig(max_output_tokens=20),
                    )
                    if test_resp and test_resp.text:
                        self.active_model = model_name
                        print(f"Gemini connected: {model_name}")
                        return
                except Exception as e:
                    print(f"Model {model_name} failed: {e}")
                    continue
            # No model worked
            print("All Gemini models exhausted or failed")
            self.client = None
        except Exception as e:
            print(f"Gemini init failed: {e}")
            self.client = None

    def reload(self):
        """Reload AI engine (e.g., after API key change)."""
        self.client = None
        self.active_model = None
        self._init_gemini()

    @property
    def is_ai_available(self):
        return self.client is not None and self.active_model is not None

    def chat(self, message):
        """Send a message and get a response. Uses Gemini if available, else fallback."""
        self.history.append({"role": "user", "text": message})

        if self.client and self.active_model:
            reply = self._try_gemini(message)
            if reply:
                self.history.append({"role": "assistant", "text": reply})
                return reply

        reply = self._fallback_response(message)
        self.history.append({"role": "assistant", "text": reply})
        return reply

    def _try_gemini(self, message, retries=2):
        """Try to get a Gemini response with retry logic across models."""
        # Refresh live context in background if stale, but use what we have now
        threading.Thread(target=self._refresh_live_context, daemon=True).start()
        system_instruction = SYSTEM_PROMPT.format(
            ai_name=load_ai_name(),
            datetime=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            live_context=self._live_context or "(Live data not yet loaded or unavailable)"
        )

        # Build conversation contents (last 10 exchanges)
        contents = []
        for entry in self.history[-20:]:
            role = "user" if entry["role"] == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part(text=entry["text"])]
                )
            )

        # Try current model, then fallback models
        models_to_try = [self.active_model] + [m for m in GEMINI_MODELS if m != self.active_model]

        for model_name in models_to_try:
            for attempt in range(retries):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            max_output_tokens=300,
                            temperature=0.7,
                        ),
                    )
                    if response and response.text:
                        # Update active model if we switched
                        if model_name != self.active_model:
                            print(f"Switched to model: {model_name}")
                            self.active_model = model_name
                        return response.text.strip()
                except Exception as e:
                    error_str = str(e)
                    if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                        # Rate limited — try next model
                        print(f"Rate limited on {model_name}, trying next...")
                        break  # Don't retry same model
                    elif '400' in error_str or 'INVALID' in error_str:
                        # Bad request — try simpler contents
                        print(f"Bad request on {model_name}: {e}")
                        break
                    else:
                        print(f"Gemini error ({model_name}): {e}")
                        if attempt < retries - 1:
                            time.sleep(1)

        return None  # All models failed

    def _fallback_response(self, message):
        """Smart fallback when Gemini is not available or rate-limited."""
        msg = message.lower().strip()

        # Greetings
        greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening', 'howdy']
        if any(msg.startswith(g) or msg == g for g in greetings):
            hour = datetime.datetime.now().hour
            if hour < 12:
                return "Good morning! How can I help you today?"
            elif hour < 17:
                return "Good afternoon! What can I do for you?"
            else:
                return "Good evening! How may I assist you?"

        # About self
        about_me = {
            'who are you': "I'm Maya, your AI desktop assistant! I can control your system, answer questions, and help with tasks.",
            'what can you do': "I can control volume & brightness, open/close apps, search the web, do math, check weather, take screenshots, and much more!",
            'what is your name': "I'm Maya, your personal AI assistant. Nice to meet you!",
            'how are you': "I'm running great! All systems operational. How about you?",
            'thank you': "You're welcome! Always happy to help.",
            'thanks': "Anytime! Let me know if you need anything else.",
        }
        for key, response in about_me.items():
            if key in msg:
                return response

        # Jokes
        if 'joke' in msg:
            jokes = [
                "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
                "There are only 10 types of people: those who understand binary and those who don't.",
                "A SQL query walks into a bar, sees two tables and asks... 'Can I JOIN you?'",
                "Why was the JavaScript developer sad? He didn't Node how to Express himself! 😄",
                "What's a programmer's favorite hangout? Foo Bar! 🍺",
            ]
            return random.choice(jokes)

        # Compliments
        if any(w in msg for w in ['love you', 'you are great', 'awesome', 'amazing']):
            return "That's so kind! You're pretty awesome yourself! 😊"

        # Default — give useful guidance
        if self.client and not self.active_model:
            return ("⚠️ Gemini API rate limit reached. I can still handle system commands! "
                    "Try: volume, brightness, open apps, weather, calculator, screenshots, system info.")
        elif not get_api_key():
            return ("Set up a free Gemini API key at aistudio.google.com/apikey, "
                    "then click ⚙️ Settings to unlock AI conversations.")
        elif not HAS_GEMINI:
            return "Install AI package: pip install google-genai"

        return ("I can handle system commands like volume, brightness, apps, weather, "
                "and math. For AI conversations, the Gemini API may be temporarily rate-limited.")
