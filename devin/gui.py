"""
Premium PyQt5 GUI for Maya AI Assistant.
Features: chat bubbles, animated waveform, system stats, modern dark theme.
Thread-safe communication via Qt signals.
"""
import sys
import os
import re
import math
import random
import shutil
import tempfile
import subprocess
import threading
import asyncio
import json
import datetime

import speech_recognition as sr

# Microsoft Edge TTS — free neural voices (online)
try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

# Google TTS fallback
try:
    from gtts import gTTS
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False

# pyttsx3 / espeak offline fallback
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

# ── Voice Presets ───────────────────────────────────────────────
# Each entry: (display_name, engine, voice_id_or_lang, rate_offset, pitch_offset)
# rate_offset/pitch_offset are Edge TTS SSML adjustments (e.g. "+10%" / "-5Hz")
VOICE_PRESETS = {
    "🧑 Andrew (US Male)":        ("edge", "en-US-AndrewNeural",      "+0%",  "+0Hz"),
    "👦 Brian (US Male, Deep)":   ("edge", "en-US-BrianNeural",       "-5%",  "-5Hz"),
    "🧔 Guy (US Male, Clear)":    ("edge", "en-US-GuyNeural",         "+0%",  "+0Hz"),
    "👨 Eric (US Male, Warm)":    ("edge", "en-US-EricNeural",        "+0%",  "+0Hz"),
    "🎙️ Ryan (UK Male)":          ("edge", "en-GB-RyanNeural",        "+0%",  "+0Hz"),
    "🏴 Thomas (UK Male)":        ("edge", "en-GB-ThomasNeural",      "+0%",  "+0Hz"),
    "🧑‍💻 Prabhat (India Male)":  ("edge", "en-IN-PrabhatNeural",     "+0%",  "+0Hz"),
    "👩 Ava (US Female)":         ("edge", "en-US-AvaNeural",         "+0%",  "+0Hz"),
    "👩 Emma (US Female)":        ("edge", "en-US-EmmaNeural",        "+0%",  "+0Hz"),
    "👩 Sonia (UK Female)":       ("edge", "en-GB-SoniaNeural",       "+0%",  "+0Hz"),
    "👩 Neerja (India Female)":   ("edge", "en-IN-NeerjaExpressiveNeural", "+0%", "+0Hz"),
    "🤖 Espeak (Offline Male)":   ("espeak", "en",                    "160",  ""),
}
DEFAULT_VOICE = "🧑 Andrew (US Male)"

CONFIG_DIR  = os.path.expanduser("~/.config/maya")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def _load_voice_config() -> str:
    """Return saved voice preset name (or default)."""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f).get("voice_preset", DEFAULT_VOICE)
    except Exception:
        return DEFAULT_VOICE


def _save_voice_config(preset_name: str):
    """Persist selected voice preset."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                config = json.load(f)
        config["voice_preset"] = preset_name
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


def _load_ai_name() -> str:
    """Return the saved AI name (defaults to 'Maya')."""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f).get("ai_name", "Maya") or "Maya"
    except Exception:
        return "Maya"


def _save_ai_name(name: str):
    """Persist the AI name to config."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                config = json.load(f)
        config["ai_name"] = name
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextBrowser, QFrame,
    QGraphicsDropShadowEffect, QDialog, QFormLayout, QDialogButtonBox,
    QSizePolicy, QScrollArea
)
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QLinearGradient, QIcon, QFontDatabase, QPainterPath
)
from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, QObject, QSize, QPropertyAnimation,
    QEasingCurve, QPoint, QRectF
)

from devin.assistant import MayaAssistant
from devin.ai_engine import get_api_key, set_api_key

# ── Colors ──────────────────────────────────────────────────────
COLORS = {
    'bg_darkest': '#060610',
    'bg_dark': '#0c0c1d',
    'bg_surface': '#12122a',
    'bg_elevated': '#1a1a3e',
    'bg_input': '#14142f',
    'primary': '#00d4aa',
    'primary_dim': '#00a888',
    'secondary': '#6366f1',
    'accent': '#f472b6',
    'text': '#e2e8f0',
    'text_dim': '#94a3b8',
    'user_bubble': '#1e2a5f',
    'assistant_bubble': '#0f1f35',
    'border': '#1e2950',
    'success': '#22c55e',
    'warning': '#f59e0b',
    'error': '#ef4444',
}


# ── AI Face Widget ──────────────────────────────────────────────
class AIFaceWidget(QWidget):
    """Futuristic holographic animated AI face visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"  # idle, listening, thinking, speaking
        self.amplitude = 0.0
        self.rotation_angle = 0.0
        self.pulse_phase = 0.0
        self.subtitle_text = ""

        # Load avatar image from assets
        import os
        from PyQt5.QtGui import QPixmap
        self.face_image = None
        self.assets_path = os.path.join(os.path.dirname(__file__), "assets", "maya_face.png")
        if os.path.exists(self.assets_path):
            self.face_image = QPixmap(self.assets_path)

        # Animation timer (targeting ~60 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(16)

    def set_state(self, state):
        if state in ["idle", "listening", "thinking", "speaking"]:
            self.state = state
            self.update()

    def set_subtitle(self, text):
        self.subtitle_text = text
        self.update()

    def _animate(self):
        # Update rotation angle based on state
        if self.state == "thinking":
            self.rotation_angle += 4.5
        elif self.state == "listening":
            self.rotation_angle += 2.5
        else:
            self.rotation_angle += 0.8

        # Breathing phase
        self.pulse_phase += 0.07

        # Generate voice visualizer ripple when speaking
        if self.state == "speaking":
            self.amplitude = 0.15 + abs(math.sin(self.pulse_phase * 3.5) * 0.5) + random.uniform(-0.1, 0.1)
            self.amplitude = max(0.05, min(1.0, self.amplitude))
        else:
            self.amplitude = 0.0

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        w, h = rect.width(), rect.height()

        # 1. Render Cybernetic Face Backdrop
        if self.face_image and not self.face_image.isNull():
            scaled_img = self.face_image.scaled(
                rect.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            cx_img = (scaled_img.width() - w) / 2
            cy_img = (scaled_img.height() - h) / 2
            painter.drawPixmap(0, 0, scaled_img, int(cx_img), int(cy_img), w, h)
        else:
            # Tech background fallback
            bg_gradient = QLinearGradient(0, 0, 0, h)
            bg_gradient.setColorAt(0.0, QColor("#04040c"))
            bg_gradient.setColorAt(1.0, QColor("#080816"))
            painter.fillRect(rect, bg_gradient)

        # Center point
        cx = w / 2
        cy = h / 2

        # 2. Select Overlay Accent Color based on AI State
        if self.state == "listening":
            glow_color = QColor(0, 212, 170, 75)       # Cyan
            accent_color = QColor(0, 212, 170, 210)
            overlay_bg = QColor(0, 15, 10, 80)
        elif self.state == "thinking":
            glow_color = QColor(244, 114, 182, 75)     # Magenta/Pink
            accent_color = QColor(244, 114, 182, 210)
            overlay_bg = QColor(15, 0, 15, 80)
        elif self.state == "speaking":
            glow_color = QColor(99, 102, 241, 75)      # Indigo
            accent_color = QColor(99, 102, 241, 210)
            overlay_bg = QColor(5, 5, 20, 80)
        else: # idle
            glow_color = QColor(245, 158, 11, 40)      # Gold
            accent_color = QColor(245, 158, 11, 130)
            overlay_bg = QColor(15, 10, 0, 50)

        # 3. Dynamic Vector Overlays (Tech Borders, HUD, Audio Line, Laser Scan)
        
        # A. Tech Corner Brackets
        pen = QPen(accent_color, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        
        margin = 16
        # Top-Left Bracket
        painter.drawLine(margin, margin, margin + 35, margin)
        painter.drawLine(margin, margin, margin, margin + 35)
        # Top-Right Bracket
        painter.drawLine(w - margin, margin, w - margin - 35, margin)
        painter.drawLine(w - margin, margin, w - margin, margin + 35)
        # Bottom-Left Bracket
        painter.drawLine(margin, h - margin, margin + 35, h - margin)
        painter.drawLine(margin, h - margin, margin, h - margin - 35)
        # Bottom-Right Bracket
        painter.drawLine(w - margin, h - margin, w - margin - 35, h - margin)
        painter.drawLine(w - margin, h - margin, w - margin, h - margin - 35)

        # B. Rotating Orbit Status HUD Ring (Top-Right Corner)
        indicator_x = w - 45
        indicator_y = 45
        painter.setBrush(overlay_bg)
        painter.setPen(QPen(accent_color, 1.2))
        painter.drawEllipse(QPoint(int(indicator_x), int(indicator_y)), 15, 15)
        
        # Small orbiting status node
        node_x = indicator_x + math.cos(self.rotation_angle * 0.05) * 10
        node_y = indicator_y + math.sin(self.rotation_angle * 0.05) * 10
        painter.setBrush(accent_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPoint(int(node_x), int(node_y)), 3, 3)

        # C. Bottom Floating Voice Reactive Audio Waveform
        mouth_y = h - 60
        mouth_w = w * 0.75
        painter.setBrush(Qt.NoBrush)

        if self.state == "speaking":
            path = QPainterPath()
            path.moveTo(cx - mouth_w / 2, mouth_y)
            steps = 22
            for i in range(steps + 1):
                x = cx - mouth_w / 2 + (mouth_w / steps) * i
                wave_y = mouth_y + math.sin(self.pulse_phase * 7.0 + i * 1.5) * (45 * self.amplitude)
                path.lineTo(x, wave_y)
            
            # Thick ambient glow
            glow_pen = QPen(glow_color, 6)
            painter.setPen(glow_pen)
            painter.drawPath(path)
            
            # Sharp core line
            pen = QPen(QColor(255, 255, 255, 240), 2)
            painter.setPen(pen)
            painter.drawPath(path)
            
        elif self.state == "listening":
            path = QPainterPath()
            path.moveTo(cx - mouth_w / 2, mouth_y)
            steps = 26
            for i in range(steps + 1):
                x = cx - mouth_w / 2 + (mouth_w / steps) * i
                wave_y = mouth_y + math.sin(self.pulse_phase * 9.5 + i * 2.2) * 4.0
                path.lineTo(x, wave_y)
            
            pen = QPen(accent_color, 1.8)
            painter.setPen(pen)
            painter.drawPath(path)
            
        elif self.state == "thinking":
            # Scanning cybernetic laser sweep line
            laser_y = cy + math.sin(self.pulse_phase * 1.3) * (h * 0.4)
            laser_grad = QLinearGradient(0, laser_y - 12, 0, laser_y + 12)
            laser_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            laser_grad.setColorAt(0.5, glow_color)
            laser_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            
            painter.fillRect(QRectF(0, laser_y - 12, w, 24), laser_grad)
            painter.setPen(QPen(accent_color, 1.2))
            painter.drawLine(0, int(laser_y), w, int(laser_y))

        # D. Floating Subtitles Overlay
        if self.subtitle_text:
            painter.setFont(QFont("Ubuntu", 11, QFont.Medium))
            painter.setPen(QColor("#e2e8f0"))
            metrics = painter.fontMetrics()
            
            max_w = w * 0.85
            text_lines = []
            words = self.subtitle_text.split(" ")
            curr_line = ""
            for w_word in words:
                test_line = curr_line + (" " if curr_line else "") + w_word
                if metrics.horizontalAdvance(test_line) < max_w:
                    curr_line = test_line
                else:
                    text_lines.append(curr_line)
                    curr_line = w_word
            if curr_line:
                text_lines.append(curr_line)

            line_h = metrics.height() + 4
            box_h = len(text_lines) * line_h + 16
            box_y = h - box_h - 20
            
            painter.setBrush(QColor(6, 6, 16, 210))
            painter.setPen(QPen(QColor("#1e2950"), 1))
            painter.drawRoundedRect(QRectF((w - max_w - 24)/2, box_y, max_w + 24, box_h), 10, 10)
            
            painter.setPen(QColor("#e2e8f0"))
            for idx, line in enumerate(text_lines):
                lx = (w - metrics.horizontalAdvance(line)) / 2
                ly = box_y + 12 + idx * line_h + metrics.ascent()
                painter.drawText(int(lx), int(ly), line)


# ── Settings Dialog ─────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Maya Settings")
        self.setMinimumSize(520, 340)
        self.resize(520, 340)
        self.setStyleSheet(f"""
            QDialog {{ background: {COLORS['bg_surface']}; color: {COLORS['text']}; border-radius: 12px; }}
            QLabel {{ color: {COLORS['text']}; font-size: 13px; }}
            QLineEdit, QComboBox {{
                background: {COLORS['bg_input']}; color: {COLORS['text']};
                border: 1px solid {COLORS['border']}; border-radius: 6px;
                padding: 7px 10px; font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {COLORS['primary']}; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {COLORS['bg_elevated']}; color: {COLORS['text']};
                selection-background-color: {COLORS['primary']};
                selection-color: {COLORS['bg_darkest']};
            }}
            QPushButton {{
                background: {COLORS['primary']}; color: {COLORS['bg_darkest']};
                font-weight: bold; border-radius: 6px; padding: 7px 18px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {COLORS['primary_dim']}; }}
            QPushButton#previewBtn {{
                background: {COLORS['secondary']}; color: white;
            }}
            QPushButton#previewBtn:hover {{ background: #818cf8; }}
        """)

        from PyQt5.QtWidgets import QTabWidget, QComboBox
        self._QComboBox = QComboBox

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {COLORS['border']}; border-radius:6px; }}
            QTabBar::tab {{
                background: {COLORS['bg_dark']}; color: {COLORS['text_dim']};
                padding: 6px 18px; border-radius: 4px 4px 0 0;
            }}
            QTabBar::tab:selected {{ background: {COLORS['bg_elevated']}; color: {COLORS['primary']}; }}
        """)

        # ── Tab 1: AI Key ──
        ai_tab = QWidget()
        ai_layout = QFormLayout(ai_tab)
        ai_layout.setSpacing(14)
        ai_layout.setContentsMargins(16, 16, 16, 16)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter your Gemini API key...")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        current_key = get_api_key()
        if current_key:
            self.api_key_input.setText(current_key)
        ai_layout.addRow("🔑 Gemini API Key:", self.api_key_input)

        info = QLabel("Free key: aistudio.google.com/apikey")
        info.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        ai_layout.addRow("", info)
        tabs.addTab(ai_tab, "🤖 AI Key")

        # ── Tab 2: Name ──
        name_tab = QWidget()
        n_layout = QFormLayout(name_tab)
        n_layout.setSpacing(14)
        n_layout.setContentsMargins(16, 16, 16, 16)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Maya, Aria, Jarvis, Nova...")
        self.name_input.setText(_load_ai_name())
        self.name_input.setMaxLength(30)
        n_layout.addRow("🏷️ Assistant Name:", self.name_input)

        name_hint = QLabel(
            "This name appears in the header, chat bubbles, and is used\n"
            "by Gemini when the AI refers to itself."
        )
        name_hint.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        name_hint.setWordWrap(True)
        n_layout.addRow("", name_hint)
        tabs.addTab(name_tab, "🏷️ Name")

        # ── Tab 3: Voice ──
        voice_tab = QWidget()
        v_layout = QVBoxLayout(voice_tab)
        v_layout.setSpacing(12)
        v_layout.setContentsMargins(16, 16, 16, 16)

        v_layout.addWidget(QLabel("🎙️ Choose Maya's voice:"))

        self.voice_combo = QComboBox()
        for name in VOICE_PRESETS:
            self.voice_combo.addItem(name)
        current = _load_voice_config()
        idx = self.voice_combo.findText(current)
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)
        v_layout.addWidget(self.voice_combo)

        engine_note = QLabel(
            "Neural voices (🧑👦👩) use Microsoft Edge TTS — require internet.\n"
            "Espeak works fully offline."
        )
        engine_note.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        engine_note.setWordWrap(True)
        v_layout.addWidget(engine_note)

        preview_btn = QPushButton("▶  Preview Voice")
        preview_btn.setObjectName("previewBtn")
        preview_btn.clicked.connect(self._preview_voice)
        v_layout.addWidget(preview_btn)
        v_layout.addStretch()
        tabs.addTab(voice_tab, "🔊 Voice")

        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _preview_voice(self):
        """Speak a short sample with the selected voice in a background thread."""
        preset_name = self.voice_combo.currentText()
        ai_name = self.name_input.text().strip() or "Maya"
        def _run():
            engine, voice_id, rate, pitch = VOICE_PRESETS[preset_name]
            sample = f"Hi! I'm {ai_name}, your AI desktop assistant. How does this voice sound?"
            if engine == "edge" and HAS_EDGE_TTS:
                _edge_speak_sync(sample, voice_id, rate, pitch)
            elif engine == "espeak":
                _espeak_speak(sample)
            elif HAS_GTTS:
                _gtts_speak(sample)
        threading.Thread(target=_run, daemon=True).start()

    def get_api_key(self):
        return self.api_key_input.text().strip()

    def get_voice_preset(self):
        return self.voice_combo.currentText()

    def get_ai_name(self):
        return self.name_input.text().strip() or "Maya"


# ── Standalone TTS helpers (called from any thread) ─────────────
def _edge_speak_sync(text: str, voice: str, rate: str, pitch: str):
    """Run Edge TTS synchronously in the calling thread."""
    async def _run():
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        try:
            communicate = edge_tts.Communicate(
                text, voice, rate=rate, pitch=pitch
            )
            await communicate.save(tmp.name)
            _play_audio(tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
    asyncio.run(_run())


def _gtts_speak(text: str, lang: str = "en", tld: str = "com"):
    """Speak with Google TTS."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
        tts.save(tmp.name)
        _play_audio(tmp.name)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _espeak_speak(text: str, voice: str = "en", rate: int = 155):
    """Speak with espeak (fully offline)."""
    if shutil.which("espeak-ng"):
        cmd = ["espeak-ng", "-v", voice, "-s", str(rate), text]
    elif shutil.which("espeak"):
        cmd = ["espeak", "-v", voice, "-s", str(rate), text]
    else:
        return
    try:
        subprocess.run(cmd, timeout=30, capture_output=True)
    except Exception:
        pass


def _play_audio(path: str):
    """Play an audio file using the best available player."""
    for player, args in [
        ("ffplay",  ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
        ("mpg123",  ["-q"]),
        ("mpv",     ["--no-video", "--really-quiet"]),
        ("aplay",   []),
    ]:
        if shutil.which(player):
            try:
                subprocess.run([player] + args + [path],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               timeout=60)
                return
            except Exception:
                continue


# ── Main Window ─────────────────────────────────────────────────
class MayaWindow(QMainWindow):
    """Premium dark-themed main window for Maya AI Assistant."""

    # Signals for thread-safe updates from worker threads
    _append_message = pyqtSignal(str, str)    # sender, text
    _update_status = pyqtSignal(str)           # status text
    _set_waveform = pyqtSignal(bool)           # active state
    _set_face_state = pyqtSignal(str)          # face state ("idle", "listening", "thinking", "speaking")
    _set_face_subtitle = pyqtSignal(str)       # face bottom subtitle text

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Maya AI — Desktop Assistant")
        self.setMinimumSize(700, 600)
        self.resize(880, 680)

        # Assistant
        self.assistant = MayaAssistant()
        self.is_listening = False
        self.is_speaking = False
        self.active_mode = True

        # TTS + STT
        self._speak_lock = threading.Lock()
        self._tts_process = None
        self._pyttsx3_engine = None
        self.recognizer = sr.Recognizer()

        # Load saved voice preset and AI name
        self._voice_preset = _load_voice_config()
        self._ai_name = _load_ai_name()

        # Apply name to window title now that self._ai_name is set
        self.setWindowTitle(f"{self._ai_name} AI — Desktop Assistant")

        self._build_ui()
        self._connect_signals()
        self._start_assistant_thread()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Apply dark theme
        self.setStyleSheet(f"""
            QMainWindow {{ background: {COLORS['bg_darkest']}; }}
            QWidget {{ background: transparent; color: {COLORS['text']}; font-family: 'Ubuntu', 'Segoe UI', sans-serif; }}
        """)

        # ── Header ──
        header = QFrame()
        header.setFixedHeight(70)
        header.setStyleSheet(f"""
            QFrame {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                      stop:0 {COLORS['bg_surface']}, stop:1 {COLORS['bg_elevated']});
                      border-bottom: 1px solid {COLORS['border']}; }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 0, 24, 0)

        # Title
        title_layout = QVBoxLayout()
        self.title_label = QLabel(f"🤖 {self._ai_name.upper()} AI")
        self.title_label.setFont(QFont("Ubuntu", 18, QFont.Bold))
        self.title_label.setStyleSheet(f"color: {COLORS['primary']}; letter-spacing: 2px;")
        subtitle = QLabel("Intelligent Desktop Assistant")
        subtitle.setFont(QFont("Ubuntu", 10))
        subtitle.setStyleSheet(f"color: {COLORS['text_dim']};")
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(subtitle)
        header_layout.addLayout(title_layout)

        header_layout.addStretch()

        # AI status badge
        self.ai_badge = QLabel("● AI Offline")
        self.ai_badge.setFont(QFont("Ubuntu", 10, QFont.Bold))
        self.ai_badge.setStyleSheet(f"""
            color: {COLORS['warning']}; background: {COLORS['bg_dark']};
            padding: 4px 12px; border-radius: 10px; border: 1px solid {COLORS['border']};
        """)
        header_layout.addWidget(self.ai_badge)

        # Chat toggle button
        self.chat_toggle_btn = QPushButton("💬")
        self.chat_toggle_btn.setFixedSize(40, 40)
        self.chat_toggle_btn.setToolTip("Toggle Chat History Panel")
        self.chat_toggle_btn.setStyleSheet(f"""
            QPushButton {{ background: {COLORS['bg_dark']}; border: 1px solid {COLORS['primary']};
                           border-radius: 20px; font-size: 16px; color: {COLORS['primary']}; }}
            QPushButton:hover {{ background: {COLORS['bg_elevated']}; }}
        """)
        self.chat_toggle_btn.clicked.connect(self._toggle_chat_panel)
        header_layout.addWidget(self.chat_toggle_btn)

        # Settings button
        settings_btn = QPushButton("⚙️")
        settings_btn.setFixedSize(40, 40)
        settings_btn.setStyleSheet(f"""
            QPushButton {{ background: {COLORS['bg_dark']}; border: 1px solid {COLORS['border']};
                           border-radius: 20px; font-size: 18px; color: {COLORS['text']}; }}
            QPushButton:hover {{ background: {COLORS['bg_elevated']}; border-color: {COLORS['primary']}; }}
        """)
        settings_btn.clicked.connect(self._show_settings)
        header_layout.addWidget(settings_btn)

        main_layout.addWidget(header)

        # ── Status Bar ──
        self.status_bar = QLabel("  🎤 Initializing...")
        self.status_bar.setFixedHeight(32)
        self.status_bar.setFont(QFont("Ubuntu", 11))
        self.status_bar.setStyleSheet(f"""
            background: {COLORS['bg_dark']}; color: {COLORS['primary']};
            padding-left: 16px; border-bottom: 1px solid {COLORS['border']};
        """)
        main_layout.addWidget(self.status_bar)

        # ── Middle Content Panel (Split Face + Chat) ──
        split_container = QWidget()
        split_layout = QHBoxLayout(split_container)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(0)

        # AI Face Widget
        self.ai_face_widget = AIFaceWidget()
        split_layout.addWidget(self.ai_face_widget, 6) # Stretch factor 6 (60%)

        # Chat Area
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        self.chat_display.setFont(QFont("Ubuntu", 12))
        self.chat_display.setStyleSheet(f"""
            QTextBrowser {{
                background: {COLORS['bg_darkest']};
                border-left: 1px solid {COLORS['border']}; padding: 16px;
                selection-background-color: {COLORS['primary_dim']};
            }}
            QScrollBar:vertical {{
                background: {COLORS['bg_dark']}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border']}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        split_layout.addWidget(self.chat_display, 4) # Stretch factor 4 (40%)

        main_layout.addWidget(split_container, 1)

        # ── Input Area ──
        input_frame = QFrame()
        input_frame.setFixedHeight(64)
        input_frame.setStyleSheet(f"""
            QFrame {{ background: {COLORS['bg_surface']}; border-top: 1px solid {COLORS['border']}; }}
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(16, 8, 16, 8)
        input_layout.setSpacing(10)

        # Voice toggle
        self.voice_btn = QPushButton("🎤")
        self.voice_btn.setFixedSize(44, 44)
        self.voice_btn.setToolTip("Toggle voice listening")
        self.voice_btn.setStyleSheet(f"""
            QPushButton {{ background: {COLORS['primary']}; border-radius: 22px;
                           font-size: 20px; color: {COLORS['bg_darkest']}; }}
            QPushButton:hover {{ background: {COLORS['primary_dim']}; }}
        """)
        self.voice_btn.clicked.connect(self._toggle_voice)
        input_layout.addWidget(self.voice_btn)

        # Text input
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type a command or ask anything...")
        self.text_input.setFont(QFont("Ubuntu", 13))
        self.text_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_input']}; color: {COLORS['text']};
                border: 1px solid {COLORS['border']}; border-radius: 22px;
                padding: 10px 20px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['primary']}; }}
            QLineEdit::placeholder {{ color: {COLORS['text_dim']}; }}
        """)
        self.text_input.returnPressed.connect(self._send_text_command)
        input_layout.addWidget(self.text_input)

        # Send button
        send_btn = QPushButton("➤")
        send_btn.setFixedSize(44, 44)
        send_btn.setStyleSheet(f"""
            QPushButton {{ background: {COLORS['secondary']}; border-radius: 22px;
                           font-size: 18px; color: white; font-weight: bold; }}
            QPushButton:hover {{ background: #818cf8; }}
        """)
        send_btn.clicked.connect(self._send_text_command)
        input_layout.addWidget(send_btn)

        main_layout.addWidget(input_frame)

        # ── Bottom Bar ──
        self.bottom_bar = QLabel(f"  {self._ai_name} v2.0 • Say \"listen\" to activate voice • Type or speak to interact")
        self.bottom_bar.setFixedHeight(24)
        self.bottom_bar.setFont(QFont("Ubuntu", 9))
        self.bottom_bar.setStyleSheet(f"background: {COLORS['bg_dark']}; color: {COLORS['text_dim']}; padding-left: 12px;")
        main_layout.addWidget(self.bottom_bar)

        # Update AI badge
        self._update_ai_badge()

    def _toggle_chat_panel(self):
        visible = self.chat_display.isVisible()
        self.chat_display.setVisible(not visible)
        if visible:
            self.chat_toggle_btn.setStyleSheet(f"""
                QPushButton {{ background: {COLORS['bg_dark']}; border: 1px solid {COLORS['border']};
                               border-radius: 20px; font-size: 16px; color: {COLORS['text_dim']}; }}
                QPushButton:hover {{ background: {COLORS['bg_elevated']}; border-color: {COLORS['primary']}; }}
            """)
        else:
            self.chat_toggle_btn.setStyleSheet(f"""
                QPushButton {{ background: {COLORS['bg_dark']}; border: 1px solid {COLORS['primary']};
                               border-radius: 20px; font-size: 16px; color: {COLORS['primary']}; }}
                QPushButton:hover {{ background: {COLORS['bg_elevated']}; }}
            """)

    def _connect_signals(self):
        self._append_message.connect(self._do_append_message)
        self._update_status.connect(self._do_update_status)
        self._set_face_state.connect(self.ai_face_widget.set_state)
        self._set_face_subtitle.connect(self.ai_face_widget.set_subtitle)
        self.assistant.ai_status_changed.connect(lambda _: self._update_ai_badge())

    def _update_ai_badge(self):
        if self.assistant.ai.is_ai_available:
            self.ai_badge.setText("● AI Online")
            self.ai_badge.setStyleSheet(f"""
                color: {COLORS['success']}; background: {COLORS['bg_dark']};
                padding: 4px 12px; border-radius: 10px; border: 1px solid {COLORS['border']};
            """)
        else:
            self.ai_badge.setText("● AI Offline")
            self.ai_badge.setStyleSheet(f"""
                color: {COLORS['warning']}; background: {COLORS['bg_dark']};
                padding: 4px 12px; border-radius: 10px; border: 1px solid {COLORS['border']};
            """)

    def _do_append_message(self, sender, text):
        """Thread-safe message append to chat display."""
        timestamp = datetime.datetime.now().strftime("%H:%M")
        text_html = text.replace('\n', '<br>')

        if sender == "You":
            html = f"""
            <div style="margin: 8px 0 8px 60px; text-align: right;">
                <div style="display: inline-block; background: {COLORS['user_bubble']};
                     border-radius: 16px 16px 4px 16px; padding: 12px 16px; max-width: 80%;">
                    <span style="color: #60a5fa; font-weight: bold; font-size: 11px;">You • {timestamp}</span><br>
                    <span style="color: {COLORS['text']}; font-size: 13px;">{text_html}</span>
                </div>
            </div>"""
        else:
            html = f"""
            <div style="margin: 8px 60px 8px 0;">
                <div style="display: inline-block; background: {COLORS['assistant_bubble']};
                     border-radius: 16px 16px 16px 4px; padding: 12px 16px; max-width: 80%;">
                    <span style="color: {COLORS['primary']}; font-weight: bold; font-size: 11px;">🤖 {self._ai_name} • {timestamp}</span><br>
                    <span style="color: {COLORS['text']}; font-size: 13px;">{text_html}</span>
                </div>
            </div>"""

        self.chat_display.append(html)
        # Auto-scroll to bottom
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _do_update_status(self, text):
        self.status_bar.setText(f"  {text}")

    def _send_text_command(self):
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        self._append_message.emit("You", text)
        # Process in background thread
        threading.Thread(target=self._process_and_respond, args=(text,), daemon=True).start()

    def _process_and_respond(self, text):
        """Process command and speak response (runs in background thread)."""
        self._set_face_state.emit("thinking")
        self._update_status.emit("💭 Thinking...")
        response = self.assistant.process_command(text)
        self._append_message.emit(self._ai_name, response)
        self._update_status.emit("🔊 Speaking...")

        # Check for exit commands
        if "Goodbye" in response and ("Shutting down" in response or "Call me when" in response):
            self._speak(response)
            QApplication.instance().quit()
            return

        self._speak(response)
        if self.active_mode:
            self._set_face_state.emit("listening")
            self._update_status.emit("🎤 Listening... (say something or type a command)")
        else:
            self._set_face_state.emit("idle")
            self._update_status.emit("💤 Standby — say 'listen' to wake me up")

    def _toggle_voice(self):
        self.active_mode = not self.active_mode
        if self.active_mode:
            self.voice_btn.setStyleSheet(f"""
                QPushButton {{ background: {COLORS['primary']}; border-radius: 22px;
                               font-size: 20px; color: {COLORS['bg_darkest']}; }}
                QPushButton:hover {{ background: {COLORS['primary_dim']}; }}
            """)
            self._set_face_state.emit("listening")
            self._update_status.emit("🎤 Listening... (say something or type a command)")
        else:
            self.voice_btn.setStyleSheet(f"""
                QPushButton {{ background: {COLORS['text_dim']}; border-radius: 22px;
                               font-size: 20px; color: {COLORS['bg_darkest']}; }}
                QPushButton:hover {{ background: {COLORS['border']}; }}
            """)
            self._set_face_state.emit("idle")
            self._update_status.emit("💤 Voice off — type commands or click 🎤 to re-enable")

    def _show_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            key = dialog.get_api_key()
            if key:
                set_api_key(key)
                self.assistant.ai.reload()
                self._update_ai_badge()
                if self.assistant.ai.is_ai_available:
                    self._append_message.emit(self._ai_name, "✅ Gemini AI connected! I'm now powered by AI. Ask me anything!")
                else:
                    self._append_message.emit(self._ai_name, "⚠️ Could not connect to Gemini. Please check the API key.")

            # Save and apply AI name
            new_name = dialog.get_ai_name()
            if new_name != self._ai_name:
                old_name = self._ai_name
                self._ai_name = new_name
                _save_ai_name(new_name)
                # Update all name-bearing UI elements
                self.setWindowTitle(f"{new_name} AI — Desktop Assistant")
                self.title_label.setText(f"🤖 {new_name.upper()} AI")
                self.bottom_bar.setText(
                    f"  {new_name} v2.0 • Say \"listen\" to activate voice • Type or speak to interact"
                )
                self._append_message.emit(
                    new_name,
                    f"✨ My name has been changed from {old_name} to {new_name}! "
                    "Nice to meet you with a fresh identity!"
                )

            # Save and apply voice preset
            preset = dialog.get_voice_preset()
            if preset != self._voice_preset:
                self._voice_preset = preset
                _save_voice_config(preset)
                engine, voice_id, rate, pitch = VOICE_PRESETS[preset]
                engine_label = "Edge TTS neural" if engine == "edge" else "espeak offline"
                self._append_message.emit(
                    self._ai_name,
                    f"🎙️ Voice changed to {preset} ({engine_label}). "
                    "I'll use it from now on!"
                )

    def _clean_text_for_speech(self, text):
        """Remove emojis, special chars, and excess whitespace for clean TTS input."""
        clean = re.sub(r'[^\w\s.,!?;:\'\-]', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _speak(self, text):
        """Dispatch TTS based on the active voice preset.
        Priority: Edge TTS neural → gTTS → espeak.
        Must be called from a worker thread."""
        if not text:
            return
        clean = self._clean_text_for_speech(text)
        if not clean:
            return

        preset = VOICE_PRESETS.get(self._voice_preset, VOICE_PRESETS[DEFAULT_VOICE])
        engine, voice_id, rate, pitch = preset

        with self._speak_lock:
            self._set_face_state.emit("speaking")
            self._set_face_subtitle.emit(text)
            try:
                if engine == "edge" and HAS_EDGE_TTS:
                    try:
                        _edge_speak_sync(clean, voice_id, rate, pitch)
                        return
                    except Exception as e:
                        print(f"Edge TTS failed ({voice_id}): {e} — falling back")
                # Fallback chain
                if HAS_GTTS:
                    try:
                        _gtts_speak(clean)
                        return
                    except Exception as e:
                        print(f"gTTS failed: {e}")
                _espeak_speak(clean)
            finally:
                self._set_face_subtitle.emit("")
                if self.active_mode:
                    self._set_face_state.emit("listening")
                else:
                    self._set_face_state.emit("idle")

    def _listen(self):
        """Listen for voice input (runs in worker thread). Returns recognized text or empty string."""
        try:
            with sr.Microphone() as source:
                self._update_status.emit("🎤 Listening...")
                self._set_face_state.emit("listening")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.recognizer.listen(source, timeout=8, phrase_time_limit=15)
                self._set_face_state.emit("thinking")
                self._update_status.emit("💭 Processing...")

            text = self.recognizer.recognize_google(audio)
            return text.strip()
        except sr.WaitTimeoutError:
            if self.active_mode:
                self._set_face_state.emit("listening")
            else:
                self._set_face_state.emit("idle")
            return ""
        except sr.UnknownValueError:
            if self.active_mode:
                self._set_face_state.emit("listening")
            else:
                self._set_face_state.emit("idle")
            return ""
        except Exception as e:
            print(f"Listen error: {e}")
            if self.active_mode:
                self._set_face_state.emit("listening")
            else:
                self._set_face_state.emit("idle")
            return ""

    def _start_assistant_thread(self):
        """Start the background assistant loop."""
        thread = threading.Thread(target=self._assistant_loop, daemon=True)
        thread.start()

    def _assistant_loop(self):
        """Main assistant loop running in background thread."""
        # Greet user
        hour = datetime.datetime.now().hour
        if hour < 12:
            greeting = "Good morning!"
        elif hour < 17:
            greeting = "Good afternoon!"
        else:
            greeting = "Good evening!"

        welcome = f"{greeting} I'm {self._ai_name}, your AI desktop assistant. How can I help you?"
        self._append_message.emit(self._ai_name, welcome)
        self._speak(welcome)
        self._update_status.emit("🎤 Listening... (say something or type a command)")
        self._set_face_state.emit("listening")

        HOTWORD = "listen"

        while True:
            try:
                if self.active_mode:
                    text = self._listen()
                    if text:
                        query_lower = text.lower().strip()
                        if "shut up" in query_lower or "stop listening" in query_lower:
                            self.active_mode = False
                            response = "Going into standby. Say 'listen' to wake me up."
                            self._append_message.emit("You", text)
                            self._append_message.emit(self._ai_name, response)
                            self._speak(response)
                            self._update_status.emit("💤 Standby — say 'listen' to wake me up")
                            self._set_face_state.emit("idle")
                            continue

                        self._append_message.emit("You", text)
                        self._process_and_respond(text)
                else:
                    # Standby: only listen for hotword
                    self._update_status.emit("💤 Standby — say 'listen' to wake me up")
                    self._set_face_state.emit("idle")
                    text = self._listen()
                    if text and HOTWORD in text.lower():
                        self.active_mode = True
                        self._append_message.emit(self._ai_name, "I'm awake! What do you need?")
                        self._speak("I'm awake! What do you need?")
                        self._update_status.emit("🎤 Listening...")
                        self._set_face_state.emit("listening")
            except Exception as e:
                print(f"Assistant loop error: {e}")
                import time
                time.sleep(1)
