import sys
import time
from devin.ai_engine import AIEngine

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

if __name__ == '__main__':
    test_intents()
