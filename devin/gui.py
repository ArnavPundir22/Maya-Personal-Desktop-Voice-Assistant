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
import datetime

import speech_recognition as sr

# Google TTS for natural voice
try:
    from gtts import gTTS
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False

# pyttsx3 as offline fallback only
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextBrowser, QFrame,
    QGraphicsDropShadowEffect, QDialog, QFormLayout, QDialogButtonBox,
    QSizePolicy, QScrollArea
)
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QLinearGradient, QIcon, QFontDatabase
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


# ── Waveform Widget ────────────────────────────────────────────
class WaveformWidget(QWidget):
    """Animated audio waveform visualizer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.num_bars = 32
        self.bar_values = [0.2] * self.num_bars
        self.target_values = [0.2] * self.num_bars
        self.is_active = False
        self.phase = 0

        self.timer = QTimer()
        self.timer.timeout.connect(self._update)
        self.timer.start(50)

    def set_active(self, active):
        self.is_active = active

    def _update(self):
        self.phase += 0.15
        for i in range(self.num_bars):
            if self.is_active:
                wave = math.sin(self.phase + i * 0.4) * 0.3
                noise = random.uniform(-0.15, 0.15)
                self.target_values[i] = max(0.08, min(1.0, 0.5 + wave + noise))
            else:
                self.target_values[i] = 0.05 + math.sin(self.phase * 0.5 + i * 0.3) * 0.04
            # Smooth interpolation
            self.bar_values[i] += (self.target_values[i] - self.bar_values[i]) * 0.3
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        bar_width = max(2, (w / self.num_bars) * 0.6)
        gap = (w - bar_width * self.num_bars) / (self.num_bars + 1)

        for i in range(self.num_bars):
            x = gap + i * (bar_width + gap)
            bar_h = self.bar_values[i] * h * 0.9
            y = (h - bar_h) / 2

            # Gradient color based on height
            ratio = self.bar_values[i]
            if self.is_active:
                r = int(0 + ratio * 100)
                g = int(212 - ratio * 40)
                b = int(170 + ratio * 80)
                color = QColor(r, g, b, int(180 + ratio * 75))
            else:
                color = QColor(100, 120, 160, 60)

            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, y, bar_width, bar_h), bar_width / 2, bar_width / 2)

        painter.end()


# ── Settings Dialog ─────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Maya Settings")
        self.setFixedSize(480, 200)
        self.setStyleSheet(f"""
            QDialog {{ background: {COLORS['bg_surface']}; color: {COLORS['text']}; border-radius: 12px; }}
            QLabel {{ color: {COLORS['text']}; font-size: 14px; }}
            QLineEdit {{ background: {COLORS['bg_input']}; color: {COLORS['text']}; border: 1px solid {COLORS['border']};
                         border-radius: 6px; padding: 8px; font-size: 13px; }}
            QLineEdit:focus {{ border-color: {COLORS['primary']}; }}
            QPushButton {{ background: {COLORS['primary']}; color: {COLORS['bg_darkest']}; font-weight: bold;
                           border-radius: 6px; padding: 8px 20px; font-size: 13px; }}
            QPushButton:hover {{ background: {COLORS['primary_dim']}; }}
        """)

        layout = QFormLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter your Gemini API key...")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        current_key = get_api_key()
        if current_key:
            self.api_key_input.setText(current_key)

        layout.addRow("🔑 Gemini API Key:", self.api_key_input)

        info = QLabel("Free key at: makersuite.google.com/app/apikey")
        info.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        layout.addRow("", info)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_api_key(self):
        return self.api_key_input.text().strip()


# ── Main Window ─────────────────────────────────────────────────
class MayaWindow(QMainWindow):
    """Premium dark-themed main window for Maya AI Assistant."""

    # Signals for thread-safe updates from worker threads
    _append_message = pyqtSignal(str, str)    # sender, text
    _update_status = pyqtSignal(str)           # status text
    _set_waveform = pyqtSignal(bool)           # active state

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Maya AI — Desktop Assistant")
        self.setMinimumSize(700, 600)
        self.resize(780, 700)

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
        title = QLabel("🤖 MAYA AI")
        title.setFont(QFont("Ubuntu", 18, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['primary']}; letter-spacing: 2px;")
        subtitle = QLabel("Intelligent Desktop Assistant")
        subtitle.setFont(QFont("Ubuntu", 10))
        subtitle.setStyleSheet(f"color: {COLORS['text_dim']};")
        title_layout.addWidget(title)
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

        # ── Chat Area ──
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        self.chat_display.setFont(QFont("Ubuntu", 12))
        self.chat_display.setStyleSheet(f"""
            QTextBrowser {{
                background: {COLORS['bg_darkest']};
                border: none; padding: 16px;
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
        main_layout.addWidget(self.chat_display, 1)

        # ── Waveform ──
        self.waveform = WaveformWidget()
        main_layout.addWidget(self.waveform)

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
        bottom = QLabel("  Maya v2.0 • Say \"listen\" to activate voice • Type or speak to interact")
        bottom.setFixedHeight(24)
        bottom.setFont(QFont("Ubuntu", 9))
        bottom.setStyleSheet(f"background: {COLORS['bg_dark']}; color: {COLORS['text_dim']}; padding-left: 12px;")
        main_layout.addWidget(bottom)

        # Update AI badge
        self._update_ai_badge()

    def _connect_signals(self):
        self._append_message.connect(self._do_append_message)
        self._update_status.connect(self._do_update_status)
        self._set_waveform.connect(self.waveform.set_active)
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
                    <span style="color: {COLORS['primary']}; font-weight: bold; font-size: 11px;">🤖 Maya • {timestamp}</span><br>
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
        self._update_status.emit("💭 Thinking...")
        response = self.assistant.process_command(text)
        self._append_message.emit("Maya", response)
        self._update_status.emit("🔊 Speaking...")

        # Check for exit commands
        if "Goodbye" in response and ("Shutting down" in response or "Call me when" in response):
            self._speak(response)
            QApplication.instance().quit()
            return

        self._speak(response)
        if self.active_mode:
            self._update_status.emit("🎤 Listening... (say something or type a command)")
        else:
            self._update_status.emit("💤 Standby — say 'listen' to wake me up")

    def _toggle_voice(self):
        self.active_mode = not self.active_mode
        if self.active_mode:
            self.voice_btn.setStyleSheet(f"""
                QPushButton {{ background: {COLORS['primary']}; border-radius: 22px;
                               font-size: 20px; color: {COLORS['bg_darkest']}; }}
                QPushButton:hover {{ background: {COLORS['primary_dim']}; }}
            """)
            self._update_status.emit("🎤 Listening... (say something or type a command)")
        else:
            self.voice_btn.setStyleSheet(f"""
                QPushButton {{ background: {COLORS['text_dim']}; border-radius: 22px;
                               font-size: 20px; color: {COLORS['bg_darkest']}; }}
                QPushButton:hover {{ background: {COLORS['border']}; }}
            """)
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
                    self._append_message.emit("Maya", "✅ Gemini AI connected! I'm now powered by AI. Ask me anything!")
                else:
                    self._append_message.emit("Maya", "⚠️ Could not connect to Gemini. Please check the API key.")

    def _clean_text_for_speech(self, text):
        """Remove emojis, special chars, and excess whitespace for clean TTS input."""
        clean = re.sub(r'[^\w\s.,!?;:\'\-]', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _speak(self, text):
        """Text-to-speech using Google TTS (natural voice) with ffplay.
        Falls back to pyttsx3/espeak if offline. Must be called from worker thread."""
        if not text:
            return

        clean = self._clean_text_for_speech(text)
        if not clean:
            return

        with self._speak_lock:
            self._set_waveform.emit(True)
            try:
                if HAS_GTTS:
                    self._speak_gtts(clean)
                elif HAS_PYTTSX3:
                    self._speak_pyttsx3(clean)
                else:
                    print("No TTS engine available")
            except Exception as e:
                print(f"TTS Error: {e}")
                # If gTTS fails (e.g. no internet), try pyttsx3 fallback
                if HAS_PYTTSX3 and HAS_GTTS:
                    try:
                        self._speak_pyttsx3(clean)
                    except Exception as e2:
                        print(f"Fallback TTS also failed: {e2}")
            finally:
                self._set_waveform.emit(False)

    def _speak_gtts(self, text):
        """Speak using Google TTS + ffplay. Natural voice quality."""
        tmp = None
        try:
            # Generate speech audio
            tts = gTTS(text=text, lang='en', slow=False)
            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            tts.save(tmp.name)
            tmp.close()

            # Play with ffplay (silent, no window)
            if shutil.which('ffplay'):
                self._tts_process = subprocess.Popen(
                    ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', tmp.name],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self._tts_process.wait()
                self._tts_process = None
            else:
                # Fallback players
                for player_cmd in [['mpg123', '-q'], ['mpv', '--no-video', '--really-quiet']]:
                    if shutil.which(player_cmd[0]):
                        proc = subprocess.Popen(
                            player_cmd + [tmp.name],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
                        proc.wait()
                        break
        finally:
            if tmp and os.path.exists(tmp.name):
                try:
                    os.unlink(tmp.name)
                except:
                    pass

    def _speak_pyttsx3(self, text):
        """Fallback: speak using pyttsx3/espeak (offline, robotic voice)."""
        if self._pyttsx3_engine is None:
            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_engine.setProperty('rate', 160)
            self._pyttsx3_engine.setProperty('volume', 1.0)
            voices = self._pyttsx3_engine.getProperty('voices')
            if voices:
                self._pyttsx3_engine.setProperty('voice', voices[0].id)
        self._pyttsx3_engine.say(text)
        self._pyttsx3_engine.runAndWait()

    def _listen(self):
        """Listen for voice input (runs in worker thread). Returns recognized text or empty string."""
        try:
            with sr.Microphone() as source:
                self._update_status.emit("🎤 Listening...")
                self._set_waveform.emit(True)
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.recognizer.listen(source, timeout=8, phrase_time_limit=15)
                self._set_waveform.emit(False)
                self._update_status.emit("💭 Processing...")

            text = self.recognizer.recognize_google(audio)
            return text.strip()
        except sr.WaitTimeoutError:
            self._set_waveform.emit(False)
            return ""
        except sr.UnknownValueError:
            self._set_waveform.emit(False)
            return ""
        except Exception as e:
            print(f"Listen error: {e}")
            self._set_waveform.emit(False)
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

        welcome = f"{greeting} I'm Maya, your AI desktop assistant. How can I help you?"
        self._append_message.emit("Maya", welcome)
        self._speak(welcome)
        self._update_status.emit("🎤 Listening... (say something or type a command)")

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
                            self._append_message.emit("Maya", response)
                            self._speak(response)
                            self._update_status.emit("💤 Standby — say 'listen' to wake me up")
                            continue

                        self._append_message.emit("You", text)
                        self._process_and_respond(text)
                else:
                    # Standby: only listen for hotword
                    self._update_status.emit("💤 Standby — say 'listen' to wake me up")
                    text = self._listen()
                    if text and HOTWORD in text.lower():
                        self.active_mode = True
                        self._append_message.emit("Maya", "I'm awake! What do you need?")
                        self._speak("I'm awake! What do you need?")
                        self._update_status.emit("🎤 Listening...")
            except Exception as e:
                print(f"Assistant loop error: {e}")
                import time
                time.sleep(1)
