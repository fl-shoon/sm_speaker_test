import asyncio
import logging
import serial.tools.list_ports
import wave

logging.basicConfig(level=logging.INFO)
utils_logger = logging.getLogger(__name__)

exit_event = asyncio.Event()

def set_exit_event():
    exit_event.set()

def is_exit_event_set():
    return exit_event.is_set()

def create_empty_wav_file(file_path):
    with wave.open(file_path, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes per sample
        wav_file.setframerate(44100)  # 44.1kHz sampling rate
        wav_file.writeframes(b'')  # Empty audio data