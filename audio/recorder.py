from utils.define import CHANNELS, RATE
from contextlib import contextmanager
from scipy.signal import butter, lfilter

import asyncio
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

        self.device_error_count = 0
        self.max_device_errors = 3

        self.SNR_THRESHOLD = 10  # Signal-to-Noise Ratio threshold
        self.NOISE_FLOOR = 100   # Minimum noise level to consider
        self.ENERGY_SCALE = 1.0 # Scale factor for energy values

    def start_stream(self):
        if self.stream is None or not self.stream.is_active():
            with suppress_stdout_stderr():
                self.stream = self.pyaudio.open(format=pyaudio.paInt16,
                                          channels=CHANNELS,
                                          rate=RATE,
                                          input=True,
                                          frames_per_buffer=self.CHUNK_SIZE)

    def stop_stream(self):
        if self.stream:
            try:
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                recorder_logger.error(f"Error stopping stream: {e}")
            finally:
                self.stream = None

    def save_audio(self, frames, filename):
        wf = wave.open(filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(frames)
        wf.close()

    def butter_bandpass(self, lowcut=300, highcut=3000, fs=16000, order=5):
        """Create a bandpass filter to focus on speech frequencies"""
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return b, a

    def apply_bandpass_filter(self, data):
        """Apply bandpass filter to focus on speech frequencies"""
        b, a = self.butter_bandpass()
        filtered_data = lfilter(b, a, data)
        return filtered_data
    
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
        try:
            energy_levels = []
            for frame in audio_frames:
                audio_chunk = np.frombuffer(frame, dtype=np.int16)
                # Apply bandpass filter
                filtered_audio = self.apply_bandpass_filter(audio_chunk)
                energy = np.sum(filtered_audio**2) / len(filtered_audio)
                energy_levels.append(energy)
            
            # Calculate more robust silence threshold
            energy_levels = np.array(energy_levels)
            self.silence_energy = np.median(energy_levels)  # Use median instead of mean
            
            # Dynamically adjust multiplier based on noise level
            if self.silence_energy < 1000:
                multiplier = 2.0  # Lower threshold for quiet environments
            elif self.silence_energy < 10000:
                multiplier = 2.5
            else:
                multiplier = 3.0  # Higher threshold for noisy environments
            
            self.energy_threshold = self.silence_energy * multiplier
            recorder_logger.info(f"Calibration complete. Silence energy: {self.silence_energy}, "
                               f"Threshold: {self.energy_threshold}, Multiplier: {multiplier}")
            
        except Exception as e:
            recorder_logger.error(f"Error in calibration: {e}")
            # Set default values if calibration fails
            self.silence_energy = 1000
            self.energy_threshold = 3000
    
    # def calibrate_energy_threshold(self, audio_frames):
    #     energy_levels = []
    #     for frame in audio_frames:
    #         audio_chunk = np.frombuffer(frame, dtype=np.int16)
    #         filtered_audio = self.butter_lowpass_filter(audio_chunk, cutoff=1000, fs=RATE)
    #         energy = np.sum(filtered_audio**2) / len(filtered_audio)
    #         energy_levels.append(energy)
        
    #     self.silence_energy = np.mean(energy_levels)
    #     multiplier = 3.5
    #     '''
    #     this value is to adjust the level of voice detection

    #     The lower the multiplier value:

    #     More sensitive to quiet sounds
    #     More likely to detect soft speech
    #     BUT also more likely to trigger on background noise
    #     Result in false stt


    #     The higher the multiplier:

    #     Less sensitive to quiet sounds
    #     More resistant to background noise
    #     BUT might miss soft speech

    #     If speech is not detected, DECREASE the multiplier.
    #     '''
    #     self.energy_threshold = self.silence_energy * multiplier
    #     recorder_logger.info(f"Calibration complete. Silence energy: {self.silence_energy}, Threshold: {self.energy_threshold}")
    
    def is_speech(self, audio_frame):
        if self.energy_threshold is None:
            return False
        # audio_chunk = np.frombuffer(audio_frame, dtype=np.int16)
        # filtered_audio = self.butter_lowpass_filter(audio_chunk, cutoff=1000, fs=RATE)
        # energy = np.sum(filtered_audio**2) / len(filtered_audio)
        # return energy > self.energy_threshold
        try:
            audio_chunk = np.frombuffer(audio_frame, dtype=np.int16)
            
            # Apply bandpass filter for speech frequencies
            filtered_audio = self.apply_bandpass_filter(audio_chunk)
            
            # Calculate signal energy
            signal_energy = np.sum(filtered_audio**2) / len(filtered_audio)
            
            # Calculate SNR
            noise_floor = max(self.silence_energy, self.NOISE_FLOOR)
            snr = 10 * np.log10(signal_energy / noise_floor) if noise_floor > 0 else 0
            
            # Use both energy threshold and SNR for detection
            return (signal_energy > self.energy_threshold * self.ENERGY_SCALE and 
                   snr > self.SNR_THRESHOLD)
            
        except Exception as e:
            recorder_logger.error(f"Error in speech detection: {e}")
            return False

    async def record_question(self, audio_player):
        tasks = set()
        try:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.start_stream()
                    break
                except Exception as e:
                    recorder_logger.error(f"Stream start attempt {attempt + 1} failed: {e}")
                    if attempt == max_retries - 1:
                        return None
                    await asyncio.sleep(1)
            recorder_logger.info("Listening... Speak your question.")

            frames = []
            silent_chunks = 0
            is_speaking = False
            total_chunks = 0
            silence_duration = 2
            max_duration = 30
            max_silent_chunks = int(silence_duration * self.CHUNKS_PER_SECOND)

            while True:
                try:
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

                except (OSError, IOError) as e:
                    recorder_logger.error(f"Stream read error: {e}")
                    self.device_error_count += 1
                    if self.device_error_count >= self.max_device_errors:
                        recorder_logger.error("Too many device errors, forcing cleanup")
                        self.stop_stream()
                        return None
                    continue
                except Exception as e:
                    recorder_logger.error(f"Unexpected error during recording: {e}")
                    return None

            if frames:
                try:
                    recorder_logger.info("Stopping recording stream for beep playback")
                    if not await self._play_beep_with_retry(audio_player):
                        recorder_logger.error("Failed to play beep after retries")
                    return b''.join(frames)

                except Exception as e:
                    recorder_logger.error(f"Error playing beep sound: {e}")
                    return b''.join(frames)
                finally:
                    try:
                        await asyncio.sleep(0.2)
                        if self.stream:
                            self.stream.start_stream()
                    except Exception as e:
                        recorder_logger.error(f"Error restarting stream: {e}")

            return None

        except KeyboardInterrupt:
            recorder_logger.info("Recording interrupted by user")
            raise
        except Exception as e:
            recorder_logger.error(f"Critical error in record_question: {e}")
            return None
        finally:
            try:
                self.stop_stream()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                        try:
                            await asyncio.wait_for(task, timeout=1.0)
                        except (asyncio.TimeoutError, asyncio.CancelledError):
                            pass
            except Exception as e:
                recorder_logger.error(f"Error in cleanup: {e}")

    async def _play_beep_with_retry(self, audio_player):
        try:
            recorder_logger.info("Playing beep sound...")
            if self.stream and self.stream.is_active():
                self.stream.stop_stream()
            
            await audio_player.play_audio(self.beep_file)
            return True
        except Exception as e:
            recorder_logger.error(f"Beep playback error: {e}")
            return False
    
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
        try:
            self.stop_stream()
            if hasattr(self, 'beep_file') and os.path.exists(self.beep_file):
                os.remove(self.beep_file)
            if self.pyaudio and (self.pyaudio._ptr is not None):  
                try:
                    active_streams = sum(1 for i in range(self.pyaudio.get_host_api_count()) 
                                    for j in range(self.pyaudio.get_device_count()))
                    if active_streams <= 1:  
                        self.pyaudio.terminate()
                except:
                    pass  
        except:
            pass