import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from devin.ai_engine import AIEngine
import time

ai = AIEngine()
# wait a bit for init
time.sleep(2)
text = "write a mail to cu240251013@coeruniversity.ac.in for thanking him for his support in a ai project"
intent = ai.extract_action(text)
print("Extracted intent:", intent)
