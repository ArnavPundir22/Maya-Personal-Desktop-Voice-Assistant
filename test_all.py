import sys
import time
from PyQt5.QtWidgets import QApplication
from devin.ai_engine import AIEngine
from devin.assistant import MayaAssistant

def test_intents():
    print("Testing AI Intent Extraction...")
    ai = AIEngine()
    time.sleep(2)
    
    prompts = [
        "disconnect from the network now",
        "turn off the speakers",
        "create a note saying I will be late, save it as late.txt, and send it to me on telegram",
        "take a picture of me",
        "can you clear out my recycle bin",
    ]
    
    for p in prompts:
        print(f"\nPrompt: {p}")
        intent = ai.extract_action(p)
        print(f"Extracted Intent: {intent}")

def test_assistant():
    print("\nTesting Regex & Fallback parsing...")
    app = QApplication(sys.argv)
    assistant = MayaAssistant()
    
    def on_status(msg):
        print(f"STATUS: {msg}")
        
    assistant.status_changed.connect(on_status)
    
    # We will mock the actual system operations to avoid side effects
    import devin.system_ops as sys_ops
    sys_ops.set_wifi = lambda state: f"MOCK: Wi-Fi set to {state}"
    sys_ops.set_bluetooth = lambda state: f"MOCK: Bluetooth set to {state}"
    sys_ops.empty_trash = lambda: "MOCK: Trash emptied"
    sys_ops.take_webcam_photo = lambda: "MOCK: Webcam photo taken"
    sys_ops.find_file = lambda fn: f"MOCK: Finding file {fn}"
    sys_ops.create_note_and_send = lambda m, f, p: f"MOCK: Note '{m}' saved to {f} and sent via {p}"
    
    prompts = [
        "take a photo",
        "empty the trash",
        "turn on wi-fi",
        "find the file resume",
        "create a note saying test, save it as test.txt and send it on telegram", # AI intent
    ]
    
    for p in prompts:
        print(f"\nCommand: {p}")
        res = assistant.process_command(p)
        print(f"Response: {res}")

if __name__ == '__main__':
    test_intents()
    test_assistant()
