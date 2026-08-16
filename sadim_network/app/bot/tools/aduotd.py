#sadim_network/app/bot/tools/aduotd.py
# tools for aduotd of sadim_network
from gtts import gTTS
import os
import uuid
class ADuOTD:
    @staticmethod
    def speak(text):
        tts = gTTS(text=text, lang='en') or gTTS(text=text, lang='ar')
        filename = f"audio_{uuid.uuid4()}.mp3"
        tts.save(filename)
        return filename

    @staticmethod
    def delete(filename):
        os.remove(filename)

    @staticmethod
    def get_all():
        return os.listdir()

    @staticmethod
    def get(filename):
        return open(filename, 'rb').read()


