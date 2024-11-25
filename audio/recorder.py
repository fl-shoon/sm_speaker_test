from utils.define import CHANNELS, RATE
from contextlib import contextmanager
from scipy.signal import butter, lfilter

import pyaudio
import os
import numpy as np
import logging
import tempfile
import wave

logging.basicConfig(level=logging.INFO)
recorder_logger = logging.getLogger(__name__)

@contextmanager
def suppress_stdout_stderr():
    """A context manager that redirects stdout and stderr to devnull"""
    try:
        null = os.open(os.devnull, os.O_RDWR)
        save_stdout, save_stderr = os.dup(1), os.dup(2)
        os.dup2(null, 1)
        os.dup2(null, 2)
        yield
    finally:
        os.dup2(save_stdout, 1)
        os.dup2(save_stderr, 2)
        os.close(null)

class PyRecorder:
    def __init__(self):
        self.stream = None
        self.beep_file = self.generate_beep_file()
        self.CHUNK_DURATION_MS = 30 
        self.CHUNK_SIZE = int(RATE * self.CHUNK_DURATION_MS / 1000)
        self.CHUNKS_PER_SECOND = 1000 // self.CHUNK_DURATION_MS
        
        self.energy_threshold = None
        self.silence_energy = None

        self.energy_window_size = 50  
        self.recent_energy_levels = []

        with suppress_stdout_stderr():
            self.pyaudio = pyaudio.PyAudio()

    def start_stream(self):
        if self.stream is None or not self.stream.is_active():
            with suppress_stdout_stderr():
                self.stream = self.pyaudio.open(format=pyaudio.paInt16,
                                          channels=CHANNELS,
                                          rate=RATE,
                                          input=True,
                                          frames_per_buffer=self.CHUNK_SIZE)

    def stop_stream(self):
        if self.stream and self.stream.is_active():
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

    def save_audio(self, frames, filename):
        wf = wave.open(filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(frames)
        wf.close()

    def butter_lowpass(self, cutoff, fs, order=5):
        nyq = 0.5 * fs
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype='low', analog=False)
        return b, a

    def butter_lowpass_filter(self, data, cutoff, fs, order=5):
        b, a = self.butter_lowpass(cutoff, fs, order=order)
        y = lfilter(b, a, data)
        return y

    def calibrate_energy_threshold(self, audio_frames):
        energy_levels = []
        for frame in audio_frames:
            audio_chunk = np.frombuffer(frame, dtype=np.int16)
            filtered_audio = self.butter_lowpass_filter(audio_chunk, cutoff=1000, fs=RATE)
            energy = np.sum(filtered_audio**2) / len(filtered_audio)
            energy_levels.append(energy)
        
        self.silence_energy = np.mean(energy_levels)
        multiplier = 3.5
        '''
        this value is to adjust the level of voice detection

        The lower the multiplier value:

        More sensitive to quiet sounds
        More likely to detect soft speech
        BUT also more likely to trigger on background noise
        Result in false stt


        The higher the multiplier:

        Less sensitive to quiet sounds
        More resistant to background noise
        BUT might miss soft speech

        If speech is not detected, DECREASE the multiplier.
        '''
        self.energy_threshold = self.silence_energy * multiplier
        recorder_logger.info(f"Calibration complete. Silence energy: {self.silence_energy}, Threshold: {self.energy_threshold}")
    
    def is_speech(self, audio_frame):
        if self.energy_threshold is None:
            return False
        audio_chunk = np.frombuffer(audio_frame, dtype=np.int16)
        filtered_audio = self.butter_lowpass_filter(audio_chunk, cutoff=1000, fs=RATE)
        energy = np.sum(filtered_audio**2) / len(filtered_audio)
        return energy > self.energy_threshold

    def record_question(self, audio_player):
        self.start_stream()
        recorder_logger.info("Listening... Speak your question.")

        frames = []
        silent_chunks = 0
        is_speaking = False
        total_chunks = 0
        silence_duration = 2
        max_duration = 30

        max_silent_chunks = int(silence_duration * self.CHUNKS_PER_SECOND)

        while True:
            data = self.stream.read(self.CHUNK_SIZE, exception_on_overflow=False)
            frames.append(data)
            total_chunks += 1

            if self.is_speech(data):
                if not is_speaking:
                    recorder_logger.info("Speech detected. Recording...")
                    is_speaking = True
                silent_chunks = 0
            else:
                silent_chunks += 1

            if is_speaking:
                if silent_chunks > max_silent_chunks:
                    recorder_logger.info(f"End of speech detected. Total chunks: {total_chunks}")
                    break
            elif total_chunks > 5 * self.CHUNKS_PER_SECOND:  
                recorder_logger.info("No speech detected. Stopping recording.")
                self.stop_stream()
                return None

            if total_chunks > max_duration * self.CHUNKS_PER_SECOND:
                recorder_logger.info(f"Maximum duration reached. Total chunks: {total_chunks}")
                break

        audio_player.play_audio(self.beep_file)
        self.stop_stream()
        return b''.join(frames)

    def generate_beep_file(self):
        duration = 0.2  # seconds
        frequency = 880  # Hz (A5 note)
        sample_rate = 44100  

        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio = np.sin(2 * np.pi * frequency * t)
        audio = (audio * 32767).astype(np.int16)

        fd, temp_path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)

        with wave.open(temp_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio.tobytes())

        return temp_path

    def __del__(self):
        self.stop_stream()
        if self.pyaudio:
            self.pyaudio.terminate()
        if hasattr(self, 'beep_file') and os.path.exists(self.beep_file):
            os.remove(self.beep_file)