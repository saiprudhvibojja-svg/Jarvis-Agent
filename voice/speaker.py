import pyttsx3
import threading
import queue

class Speaker:
    def __init__(self):
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._worker, daemon=False, name="jarvis-tts")
        self.thread.start()
    
    def _worker(self):
        # Engine MUST be created in this thread
        engine = pyttsx3.init()
        engine.setProperty('rate', 165)
        engine.setProperty('volume', 1.0)
        # Try to find a good voice
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'david' in voice.name.lower() or 'mark' in voice.name.lower():
                engine.setProperty('voice', voice.id)
                break
        
        while True:
            text = self.queue.get()
            if text is None:
                break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print(f"TTS error: {e}")
            self.queue.task_done()
    
    def speak(self, text: str):
        # Clean text before speaking
        clean = text.replace('✅','').replace('⚠️','').replace('❌','').replace('#','').replace('*','')
        self.queue.put(clean[:500])  # max 500 chars
    
    def shutdown(self):
        self.queue.put(None)
