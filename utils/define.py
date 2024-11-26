from utils.utils import *
from enum import Enum, auto

import os
import pyaudio

# Get the current directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Get the parent directory
PARENT_DIR = os.path.dirname(CURRENT_DIR)

# Define the assets directory
ASSETS_DIR = os.path.join(PARENT_DIR, 'assets')

# Define subdirectories for different types of assets
AUDIO_DIR = os.path.join(ASSETS_DIR, 'audio')
IMAGE_DIR = os.path.join(ASSETS_DIR, 'images')
GIF_DIR = os.path.join(ASSETS_DIR, 'gifs')
VOICE_TRIGGER_DIR = os.path.join(ASSETS_DIR, 'trigger')

# Define the temporary ai output audio file
TEMP_AUDIO_FILE = os.path.join(AUDIO_DIR, 'output.wav')

# Check if temporary audio file exists, create it if it doesn't
if not os.path.exists(TEMP_AUDIO_FILE):
    create_empty_wav_file(TEMP_AUDIO_FILE)

# Audio settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000 # Higher rates require more CPU power to process in real-time
RECORD_SECONDS = 8

# audio
ResponseAudio = os.path.join(AUDIO_DIR, "response_audio.wav") 
TriggerAudio = os.path.join(AUDIO_DIR, "startUp.wav")
ErrorAudio = os.path.join(AUDIO_DIR, "errorSpeech.wav")
AIOutputAudio = TEMP_AUDIO_FILE

# display
SpeakingGif = os.path.join(GIF_DIR, "speakingGif.gif")
SeamanLogo = os.path.join(IMAGE_DIR, "logo.png")
SatoruHappy = os.path.join(IMAGE_DIR, "happy.png")

# serial/display Settings
BautRate = '230400'

# voice trigger 
PicoLangLib = os.path.join(VOICE_TRIGGER_DIR,"libpv_porcupine.so")
PicoLangModel = os.path.join(VOICE_TRIGGER_DIR,"pico_voice_language_model_ja.pv")
PicoWakeWordKonnichiwa = os.path.join(VOICE_TRIGGER_DIR,"pico_voice_wake_word_konnichiwa.ppn") 
PicoWakeWordSatoru = os.path.join(VOICE_TRIGGER_DIR,"pico_voice_wake_word_satoru.ppn") 
ToshibaVoiceDictionary = os.path.join(VOICE_TRIGGER_DIR,"toshiba_voice_dict_jaJP.vtdic")
ToshibaVoiceLibrary = os.path.join(VOICE_TRIGGER_DIR,"libVT_ARML64h.so")

class WakeWordType(str, Enum):
    TRIGGER = auto()
    SCHEDULE = auto()
    OTHER = auto()
