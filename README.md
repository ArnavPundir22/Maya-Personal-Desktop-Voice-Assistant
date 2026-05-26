# 🤖 Maya AI — Personal Desktop Voice Assistant
### *Ubuntu / Linux Edition v2.0*

[![OS](https://img.shields.io/badge/OS-Ubuntu%20%2F%20Linux-orange?style=flat-square&logo=ubuntu)](https://ubuntu.com/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![UI](https://img.shields.io/badge/UI-PyQt5-purple?style=flat-square&logo=qt)](https://www.qt.io/)
[![Engine](https://img.shields.io/badge/AI%20Engine-Gemini%202.5-green?style=flat-square&logo=google-gemini)](https://aistudio.google.com/)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?style=flat-square&logo=github)](https://github.com/ArnavPundir22/Maya-Personal-Desktop-Voice-Assistant/tree/main)

Maya is a modern, high-performance, dark-themed personal desktop voice assistant developed for **Ubuntu Linux**. It blends natural language processing via Google's Gemini models with robust system-level automation to provide a fluid, hands-free computing experience. 

Featuring a premium **PyQt5 dashboard**, **animated audio waveforms**, and an intelligent **offline fallback system**, Maya lets you control system parameters, search the web, ask general queries, and launch applications using voice or text.

---

## 🎨 Preview & UI Highlights
<p align="center">
  <img src="devin/assets/maya_face.png" width="380" alt="Maya Cyber Face Avatar">
</p>

- **Glassmorphism Theme:** A sleek, curated dark aesthetic built with modern typography and gradients.
- **Cybernetic AI Face Backdrop:** Animated cyberpunk-style avatar with glowing cybernetic lines, revolving HUD status indicators, reactive audio waveform mouth movements, and laser thinking scanners.
- **Focus & Full Face Modes:** Click the chat toggle button (`💬`) to slide out the text chat panel, instantly switching between split-screen dashboard and pure voice face focus modes.
- **Thread-Safe Chat Bubbles:** Separate styled blocks for user queries and Maya's responses.
- **Settings Dialog:** Customize the assistant's name, switch between Edge TTS neural voice engines, and securely update your Gemini API Key.

---

## ⚡ Features

### 1. 🧠 Multi-Layer AI Engine
*   **Gemini Integration:** Powered by the new `google-genai` SDK. Automatically queries `gemini-2.5-flash` (and falls back to `gemini-2.0-flash-lite`, `gemini-2.0-flash`, etc.) to handle rate limits or regional quota differences.
*   **Rule-Based Smart Fallback:** When offline or when API limits are reached, Maya handles core interactions, greetings, programming jokes, and system actions smoothly without crashing.

### 2. 🖥️ OS & Hardware Automation
*   🔊 **Audio & Volume:** Real-time volume management via PulseAudio (`pulsectl`) or ALSA (`amixer`). Adjust to specific values, mute, unmute, or use relative commands ("louder", "quieter").
*   💡 **Screen Brightness:** Precise brightness adjustments via GNOME D-Bus (`gdbus`) or `xrandr` software dimming.
*   📸 **Screenshots:** Captures the full screen and saves it directly to `~/Pictures/` using `gnome-screenshot` or `scrot`.
*   🔒 **Lock System:** Locks the desktop session instantly using standard system services (`loginctl`).

### 3. 📦 App & Media Management
*   🚀 **App Launcher:** Opens core system apps (Terminal, File Manager, VS Code, Browser, Text Editor, Calculator) using an optimized matching registry.
*   ❌ **Process Terminator:** Closes running processes cleanly by name using `psutil`.
*   📺 **Media Playback:** Pause, resume, skip, or change tracks for MPRIS-compatible players (Spotify, VLC, Chrome) using `playerctl` or `xdotool` key signals.

### 4. 🌐 Web & Utilities
*   🌐 **Web Scraping:** Automatically detects URLs in messages, fetches clean content by removing script/nav/header boilerplate, and lets the Gemini AI analyze/summarize page details.
*   🔍 **Web Search:** Instantly trigger Google searches or search and play video content directly on YouTube.
*   📚 **Wikipedia:** Pulls concise, two-sentence summaries on any query topic.
*   🌤️ **Real-Time Weather:** Retrieves instant weather reports for your location or any specified city using `wttr.in`.
*   🔢 **Safe Calculator:** Parses and evaluates mathematical expressions using a secure evaluation sandbox.

---

## 🛠️ Project Structure

```text
Maya-Personal-Desktop-Voice-Assistant/
├── run.py                 # Application launcher and GUI entry point
├── requirements.txt       # Python library dependencies
├── README.md              # Project documentation
└── devin/                 # Package directory
    ├── __init__.py        # Versioning & package definition
    ├── assets/            # Graphical assets and UI backdrops
    │   └── maya_face.png  # Futuristic cyberpunk avatar face
    ├── ai_engine.py       # Google Gemini integration and fallback logic
    ├── assistant.py       # Core command routing and regex parser
    ├── gui.py             # Premium PyQt5 UI, Threads & Face logic
    └── system_ops.py      # Ubuntu system shell wrappers and utilities
```

---

## 📥 Installation

### 1. Install Ubuntu System Dependencies
To enable mic recording, audio playback, screenshot utilities, and media controls, run:

```bash
sudo apt update
sudo apt install -y python3-pyaudio portaudio19-dev ffmpeg ffplay playerctl xdotool scrot gnome-screenshot
```

> [!NOTE]
> `ffplay` (part of `ffmpeg`) is recommended for crystal-clear playback of the natural Google TTS voice engine.

### 2. Set Up Virtual Environment & Dependencies
Navigate to the repository folder, activate a virtual environment, and install the Python dependencies:

```bash
# Clone the repository (if not already local)
git clone https://github.com/ArnavPundir22/Maya-Personal-Desktop-Voice-Assistant.git
cd Maya-Personal-Desktop-Voice-Assistant

# Create & activate a virtual environment
python3 -m venv venv
source venv/bin/env/activate  # Or 'source venv/bin/activate'

# Install requirements
pip install -r requirements.txt
```

---

## 🚀 How to Use

### Launching the Assistant
Make sure your virtual environment is active, then run:

```bash
python run.py
```

### Interaction Modes
*   **Voice Control:** Click the 🎤 button to toggle voice input. Calibrate mic and speak. Alternatively, if Maya is in Standby mode, simply say **"listen"** to wake her up!
*   **Standby / Silent Mode:** Say **"stop listening"** or **"shut up"** to place Maya in Standby (or click the microphone icon). She will only run text commands and won't capture ambient voice until wake words are heard.
*   **Text Control:** Type your commands in the bottom input bar and press **Enter** or click the send (➤) icon.

### 🔑 Connecting Google Gemini AI
1. Go to [Google AI Studio](https://aistudio.google.com/) and grab a free API Key.
2. In the Maya dashboard, click the **⚙️ (Settings)** icon in the top right.
3. Paste your key and click **OK**.
4. Once connected, the status badge will switch to **● AI Online**, unlocking natural AI chat!

---

## 🗣️ Voice & Text Command Reference

| Action | Example Command | Command Variants |
| :--- | :--- | :--- |
| **System Info** | "Show system status" | *cpu usage, ram usage, disk space, battery* |
| **Volume Control** | "Set volume to 75" | *volume up, volume down, louder, mute, unmute* |
| **Brightness Control** | "Set brightness to 50" | *brightness up, dimmer, brighter* |
| **Open Applications** | "Open VS Code" | *open browser, open terminal, open youtube.com* |
| **Close Applications** | "Close Firefox" | *close notepad, close browser, stop spotify* |
| **Take Screenshot** | "Take a screenshot" | *screenshot, capture screen* |
| **Math calculations** | "Calculate 15 * (48 / 6)" | *solve, what is, compute* |
| **Real-time Weather** | "Weather in London" | *weather, current weather* |
| **Wikipedia Info** | "Wikipedia Python programming" | *wiki Albert Einstein* |
| **Web Searching** | "Search for Ubuntu tips" | *google machine learning, look up rust lang* |
| **Play YouTube** | "Play lo-fi on YouTube" | *play synthwave on youtube* |
| **Media Playback** | "Next song" | *pause music, resume, skip, previous track* |
| **Lock Screen** | "Lock my computer" | *lock screen, lock pc* |
| **Deactivate Voice** | "Stop listening" | *shut up, standby* |
| **General Chat** | "Who are you?" | *tell me a joke, general trivia questions* |
| **Shutdown Maya** | "Goodbye" | *exit, quit, close maya* |

---

## 📄 License
This project is proprietary and confidential. All rights are reserved by Arnav Pundir. See the `LICENSE` file for details.

---

*Developed by **Arnav Pundir** &mdash; Enjoy using Maya!*
