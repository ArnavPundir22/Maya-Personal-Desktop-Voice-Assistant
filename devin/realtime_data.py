"""
Real-Time Data Module for Maya AI Assistant.

Provides live feeds for:
  - Weather (OpenWeatherMap API → wttr.in fallback)
  - News headlines (NewsAPI → RSS/Google News fallback)
  - Cryptocurrency prices (CoinGecko – free, no key needed)
  - Stock quotes (Yahoo Finance API – free, no key needed)
  - Public holidays / calendar events (Nager.Date – free)
  - Sunrise/Sunset times (Open-Meteo – free)

All functions return human-readable strings, ready for Maya to speak.
"""

import os
import json
import time
import datetime
import requests

CONFIG_DIR = os.path.expanduser("~/.config/maya")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# ── Simple in-memory cache ──────────────────────────────────────
_cache: dict = {}
CACHE_TTL = {
    "weather":   600,   # 10 min
    "news":      300,   # 5 min
    "crypto":    60,    # 1 min
    "stocks":    120,   # 2 min
    "holiday":   86400, # 1 day
    "sun":       3600,  # 1 hour
}


def _cached(key: str, ttl_key: str, fn):
    """Return cached value or compute & cache a new one."""
    now = time.time()
    if key in _cache:
        val, ts = _cache[key]
        if now - ts < CACHE_TTL.get(ttl_key, 300):
            return val
    val = fn()
    _cache[key] = (val, now)
    return val


# ── Config helpers ──────────────────────────────────────────────
def _load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def get_owm_api_key() -> str:
    return os.environ.get("OWM_API_KEY", "") or _load_config().get("owm_api_key", "")


def get_news_api_key() -> str:
    return os.environ.get("NEWS_API_KEY", "") or _load_config().get("news_api_key", "")


def save_api_keys(**kwargs):
    """Save one or more API keys to config (e.g., owm_api_key='...', news_api_key='...')."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    config = _load_config()
    config.update(kwargs)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


# ═══════════════════════════════════════════════════════════════
#  WEATHER
# ═══════════════════════════════════════════════════════════════

def get_weather_detailed(city: str = "") -> str:
    """
    Fetch current weather with temperature, feels-like, humidity,
    wind speed, and a short description.

    Uses OpenWeatherMap (if API key configured) → wttr.in as fallback.
    """
    city = city.strip()

    def _fetch():
        owm_key = get_owm_api_key()
        if owm_key:
            return _owm_weather(city, owm_key)
        return _wttr_weather(city)

    cache_key = f"weather_{city}"
    return _cached(cache_key, "weather", _fetch)


def _owm_weather(city: str, api_key: str) -> str:
    """Fetch weather from OpenWeatherMap."""
    try:
        q = city if city else _get_user_city()
        url = "https://api.openweathermap.org/data/2.5/weather"
        resp = requests.get(
            url,
            params={"q": q, "appid": api_key, "units": "metric"},
            timeout=8,
        )
        if resp.status_code == 200:
            d = resp.json()
            name = d.get("name", q)
            desc = d["weather"][0]["description"].capitalize()
            temp = d["main"]["temp"]
            feels = d["main"]["feels_like"]
            humidity = d["main"]["humidity"]
            wind = d["wind"]["speed"]
            return (
                f"🌍 {name}: {desc}. 🌡️ {temp:.1f}°C (feels like {feels:.1f}°C). "
                f"💧 Humidity: {humidity}%. 💨 Wind: {wind} m/s."
            )
        elif resp.status_code == 404:
            return f"City '{city}' not found. Try a different city name."
    except Exception as e:
        pass
    return _wttr_weather(city)


def _wttr_weather(city: str) -> str:
    """Fallback: fetch weather from wttr.in."""
    try:
        url = f"https://wttr.in/{city}?format=%l:+%C,+%t+(feels+%f),+Humidity:+%h,+Wind:+%w"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "curl"})
        if resp.status_code == 200:
            return "🌤️ " + resp.text.strip()
    except Exception:
        pass
    return "Could not fetch weather. Check your internet connection."


def get_weather_forecast(city: str = "", days: int = 3) -> str:
    """Fetch a multi-day weather forecast (requires OpenWeatherMap key)."""
    city = city.strip()
    owm_key = get_owm_api_key()
    if not owm_key:
        return "Weather forecast requires an OpenWeatherMap API key. Set one with: set weather key YOUR_KEY"

    def _fetch():
        try:
            q = city if city else _get_user_city()
            url = "https://api.openweathermap.org/data/2.5/forecast"
            resp = requests.get(
                url,
                params={"q": q, "appid": owm_key, "units": "metric", "cnt": days * 8},
                timeout=8,
            )
            if resp.status_code != 200:
                return f"Could not fetch forecast for '{q}'."
            data = resp.json()
            city_name = data["city"]["name"]
            # Group by day
            days_seen = {}
            for entry in data["list"]:
                dt = datetime.datetime.fromtimestamp(entry["dt"])
                day_str = dt.strftime("%A, %b %d")
                if day_str not in days_seen:
                    days_seen[day_str] = {
                        "temps": [],
                        "desc": entry["weather"][0]["description"],
                    }
                days_seen[day_str]["temps"].append(entry["main"]["temp"])
                if dt.hour == 12:
                    days_seen[day_str]["desc"] = entry["weather"][0]["description"]

            lines = [f"📅 {days}-day forecast for {city_name}:"]
            for i, (day, info) in enumerate(days_seen.items()):
                if i >= days:
                    break
                lo = min(info["temps"])
                hi = max(info["temps"])
                desc = info["desc"].capitalize()
                lines.append(f"  • {day}: {desc}, {lo:.0f}°C – {hi:.0f}°C")
            return "\n".join(lines)
        except Exception as e:
            return f"Forecast error: {e}"

    return _cached(f"forecast_{city}_{days}", "weather", _fetch)


def _get_user_city() -> str:
    """Best-effort IP-based city detection."""
    try:
        resp = requests.get("https://ipapi.co/json/", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("city", "")
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════════════════════════════
#  NEWS
# ═══════════════════════════════════════════════════════════════

def get_news(topic: str = "", count: int = 5) -> str:
    """
    Fetch top news headlines.
    Uses NewsAPI (if key configured) → Google News RSS fallback.
    """
    def _fetch():
        news_key = get_news_api_key()
        if news_key:
            return _newsapi_headlines(topic, count, news_key)
        return _rss_headlines(topic, count)

    cache_key = f"news_{topic}_{count}"
    return _cached(cache_key, "news", _fetch)


def _newsapi_headlines(topic: str, count: int, api_key: str) -> str:
    """Fetch from NewsAPI.org."""
    try:
        if topic:
            url = "https://newsapi.org/v2/everything"
            params = {"q": topic, "pageSize": count, "sortBy": "publishedAt", "apiKey": api_key}
        else:
            url = "https://newsapi.org/v2/top-headlines"
            params = {"country": "us", "pageSize": count, "apiKey": api_key}

        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code == 200:
            articles = resp.json().get("articles", [])
            if not articles:
                return f"No news found for '{topic}'." if topic else "No news available."
            header = f"📰 Top {min(count, len(articles))} news"
            header += f" about '{topic}':" if topic else " headlines:"
            lines = [header]
            for i, a in enumerate(articles[:count], 1):
                title = a.get("title", "No title")
                source = a.get("source", {}).get("name", "")
                lines.append(f"  {i}. {title}" + (f" [{source}]" if source else ""))
            return "\n".join(lines)
    except Exception:
        pass
    return _rss_headlines(topic, count)


def _rss_headlines(topic: str, count: int) -> str:
    """Fallback: parse Google News RSS (no key needed)."""
    try:
        try:
            import feedparser
            has_feedparser = True
        except ImportError:
            has_feedparser = False

        if has_feedparser:
            q = topic.replace(" ", "+") if topic else "top+news"
            url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            entries = feed.entries[:count]
            if entries:
                header = f"📰 Top news" + (f" about '{topic}':" if topic else ":")
                lines = [header]
                for i, e in enumerate(entries, 1):
                    title = e.get("title", "No title")
                    # Google News RSS appends source in title as " - Source"
                    lines.append(f"  {i}. {title}")
                return "\n".join(lines)

        # Ultra-fallback: raw requests RSS parse
        q = topic.replace(" ", "+") if topic else "top+news"
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            import re
            titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", resp.text)
            titles = [t for t in titles if "Google News" not in t][:count]
            if titles:
                header = f"📰 Top news" + (f" about '{topic}':" if topic else ":")
                lines = [header] + [f"  {i}. {t}" for i, t in enumerate(titles, 1)]
                return "\n".join(lines)
    except Exception as e:
        pass
    return "Could not fetch news. Check your internet connection."


# ═══════════════════════════════════════════════════════════════
#  CRYPTOCURRENCY
# ═══════════════════════════════════════════════════════════════

CRYPTO_IDS = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "solana": "solana", "sol": "solana",
    "cardano": "cardano", "ada": "cardano",
    "ripple": "ripple", "xrp": "ripple",
    "binancecoin": "binancecoin", "bnb": "binancecoin",
    "litecoin": "litecoin", "ltc": "litecoin",
    "polkadot": "polkadot", "dot": "polkadot",
    "avalanche": "avalanche-2", "avax": "avalanche-2",
    "chainlink": "chainlink", "link": "chainlink",
    "uniswap": "uniswap", "uni": "uniswap",
    "matic": "matic-network", "polygon": "matic-network",
}


def get_crypto_price(coin: str = "bitcoin") -> str:
    """Get real-time cryptocurrency price from CoinGecko (free, no key needed)."""
    coin_lower = coin.lower().strip()
    coin_id = CRYPTO_IDS.get(coin_lower, coin_lower)

    def _fetch():
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            resp = requests.get(
                url,
                params={"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true"},
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                if coin_id in data:
                    price = data[coin_id]["usd"]
                    change = data[coin_id].get("usd_24h_change", 0)
                    arrow = "📈" if change >= 0 else "📉"
                    return (
                        f"💰 {coin.capitalize()}: ${price:,.2f} USD  "
                        f"{arrow} {change:+.2f}% (24h)"
                    )
                return f"Coin '{coin}' not found on CoinGecko."
        except Exception as e:
            return f"Could not fetch crypto price: {e}"
        return "Could not fetch crypto data."

    return _cached(f"crypto_{coin_id}", "crypto", _fetch)


def get_crypto_market_overview(limit: int = 5) -> str:
    """Get top N cryptocurrencies by market cap."""
    def _fetch():
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            resp = requests.get(
                url,
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": limit,
                    "page": 1,
                    "sparkline": "false",
                },
                timeout=8,
            )
            if resp.status_code == 200:
                coins = resp.json()
                lines = [f"📊 Top {limit} cryptos by market cap:"]
                for c in coins:
                    change = c.get("price_change_percentage_24h", 0) or 0
                    arrow = "📈" if change >= 0 else "📉"
                    lines.append(
                        f"  • {c['name']} ({c['symbol'].upper()}): "
                        f"${c['current_price']:,.2f}  {arrow}{change:+.1f}%"
                    )
                return "\n".join(lines)
        except Exception as e:
            pass
        return "Could not fetch crypto market overview."

    return _cached(f"crypto_market_{limit}", "crypto", _fetch)


# ═══════════════════════════════════════════════════════════════
#  STOCKS
# ═══════════════════════════════════════════════════════════════

def get_stock_price(ticker: str) -> str:
    """
    Get real-time stock price using Yahoo Finance (unofficial JSON API).
    No API key needed.
    """
    ticker = ticker.upper().strip()

    def _fetch():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                meta = data["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice", 0)
                prev_close = meta.get("chartPreviousClose", price)
                change = price - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0
                currency = meta.get("currency", "USD")
                name = meta.get("longName") or meta.get("shortName") or ticker
                arrow = "📈" if change >= 0 else "📉"
                return (
                    f"📊 {name} ({ticker}): {currency} {price:.2f}  "
                    f"{arrow} {change:+.2f} ({change_pct:+.2f}%)"
                )
            return f"Could not find stock ticker '{ticker}'."
        except Exception as e:
            return f"Stock lookup error: {e}"

    return _cached(f"stock_{ticker}", "stocks", _fetch)


# ═══════════════════════════════════════════════════════════════
#  SUNRISE / SUNSET
# ═══════════════════════════════════════════════════════════════

def get_sun_times(city: str = "") -> str:
    """Get today's sunrise and sunset times using Open-Meteo (free, no key)."""
    def _fetch():
        try:
            # Step 1: Geocode city → lat/lon
            lat, lon, place = _geocode_city(city)
            if lat is None:
                return "Could not locate your city for sun times."

            # Step 2: Fetch sunrise/sunset from Open-Meteo
            url = "https://api.open-meteo.com/v1/forecast"
            resp = requests.get(
                url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "sunrise,sunset",
                    "timezone": "auto",
                    "forecast_days": 1,
                },
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                sunrise_iso = data["daily"]["sunrise"][0]
                sunset_iso = data["daily"]["sunset"][0]
                sr = datetime.datetime.fromisoformat(sunrise_iso).strftime("%I:%M %p")
                ss = datetime.datetime.fromisoformat(sunset_iso).strftime("%I:%M %p")
                return f"☀️ {place} — Sunrise: {sr}, Sunset: {ss}"
        except Exception as e:
            pass
        return "Could not fetch sun times."

    return _cached(f"sun_{city}", "sun", _fetch)


def _geocode_city(city: str):
    """Geocode a city name → (lat, lon, display_name). Returns (None,None,None) on failure."""
    try:
        if not city:
            # IP-based location
            resp = requests.get("https://ipapi.co/json/", timeout=5)
            if resp.status_code == 200:
                d = resp.json()
                return float(d["latitude"]), float(d["longitude"]), d.get("city", "your city")
        else:
            url = "https://nominatim.openstreetmap.org/search"
            resp = requests.get(
                url,
                params={"q": city, "format": "json", "limit": 1},
                headers={"User-Agent": "MayaAssistant/1.0"},
                timeout=5,
            )
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    r = results[0]
                    return float(r["lat"]), float(r["lon"]), r.get("display_name", city).split(",")[0]
    except Exception:
        pass
    return None, None, None


# ═══════════════════════════════════════════════════════════════
#  PUBLIC HOLIDAYS
# ═══════════════════════════════════════════════════════════════

def get_upcoming_holidays(country_code: str = "IN", count: int = 3) -> str:
    """Get upcoming public holidays for a country (uses Nager.Date API, free)."""
    def _fetch():
        try:
            year = datetime.datetime.now().year
            url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code.upper()}"
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                holidays = resp.json()
                today = datetime.date.today()
                upcoming = [
                    h for h in holidays
                    if datetime.date.fromisoformat(h["date"]) >= today
                ][:count]
                if not upcoming:
                    return f"No upcoming public holidays found for {country_code.upper()} this year."
                lines = [f"🎉 Upcoming holidays in {country_code.upper()}:"]
                for h in upcoming:
                    d = datetime.date.fromisoformat(h["date"])
                    days_away = (d - today).days
                    when = f"in {days_away} days" if days_away > 0 else "today!"
                    lines.append(f"  • {h['localName']} — {d.strftime('%b %d, %Y')} ({when})")
                return "\n".join(lines)
        except Exception:
            pass
        return "Could not fetch holiday information."

    return _cached(f"holiday_{country_code}", "holiday", _fetch)


# ═══════════════════════════════════════════════════════════════
#  QUICK CONTEXT SNAPSHOT (used to inject into AI system prompt)
# ═══════════════════════════════════════════════════════════════

def get_live_context_snippet() -> str:
    """
    Returns a compact real-time context string to inject into the AI system prompt.
    Fetches weather + top news headlines quickly (uses cache aggressively).
    """
    parts = []
    try:
        weather = get_weather_detailed("")
        parts.append(f"Current weather: {weather}")
    except Exception:
        pass

    try:
        news = get_news(count=3)
        parts.append(f"Latest news:\n{news}")
    except Exception:
        pass

    return "\n".join(parts) if parts else ""
