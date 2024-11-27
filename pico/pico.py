from contextlib import contextmanager
from utils.define import *

import logging
import numpy as np
import pvporcupine
import pyaudio
import signal
import time
import threading

logging.basicConfig(level=logging.INFO)
pico_logger = logging.getLogger(__name__)

@contextmanager
def time_limit(seconds):
    def signal_handler(signum, frame):
        raise TimeoutError(f"Timed out after {seconds} seconds")
    
    # Set the signal handler and a alarm
    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        # Disable the alarm
        signal.alarm(0)

class PicoVoiceTrigger:
    def __init__(self, args):
        self.porcupine = None
        self.audio = None
        self.audio_stream = None
        self.gain = args.gain if hasattr(args, 'gain') else 5.0
        self.frame_length = None
        self._lock = threading.Lock()
        self.args = args
        self.device_index = 0 

        max_retries = 3
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                # Force release audio device before initialization
                self._force_release_audio()
                time.sleep(0.5)  # Wait for device to be released
                
                if self.initialize(args):
                    break
            except Exception as e:
                last_error = e
                retry_count += 1
                pico_logger.error(f"Initialization attempt {retry_count} failed: {e}")
                time.sleep(1)  # Wait before retrying

        if retry_count >= max_retries:
            pico_logger.error(f"Failed to initialize after {max_retries} attempts. Last error: {last_error}")
            raise RuntimeError(f"Failed to initialize PicoVoice after {max_retries} attempts")

    def _force_release_audio(self):
        """Release audio device with system-independent approach"""
        try:
            # Clean up any existing streams
            if self.audio_stream:
                try:
                    if hasattr(self.audio_stream, 'is_active') and self.audio_stream.is_active():
                        self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except:
                    pass
                self.audio_stream = None

            if self.audio:
                try:
                    self.audio.terminate()
                except:
                    pass
                self.audio = None

            # Wait for device to be released
            time.sleep(1.0)
            
            # Try to kill any process using audio device
            try:
                os.system('fuser -k /dev/snd/* 2>/dev/null || true')
            except:
                pass
            time.sleep(0.5)

        except Exception as e:
            pico_logger.error(f"Error during audio device release: {e}")

    def _initialize_audio(self):
        """Initialize audio with device locking"""
        try:
            # Force release first
            self._force_release_audio()
            
            # Create lock file to prevent other processes from accessing the device
            lock_file = "/tmp/audio_device.lock"
            try:
                with open(lock_file, 'x') as f:  # exclusive creation
                    f.write(str(os.getpid()))
            except FileExistsError:
                # If lock exists, check if process is still running
                try:
                    with open(lock_file, 'r') as f:
                        pid = int(f.read().strip())
                    os.kill(pid, 0)  # Check if process exists
                    pico_logger.error("Audio device in use by another process")
                    return False
                except (OSError, ValueError):
                    # Process not running or invalid PID, remove lock
                    try:
                        os.remove(lock_file)
                        with open(lock_file, 'x') as f:
                            f.write(str(os.getpid()))
                    except:
                        pass

            try:
                # Initialize PyAudio
                self.audio = pyaudio.PyAudio()
                
                # Test with minimal configuration first
                test_stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    frames_per_buffer=256,
                    input=True,
                    input_device_index=self.device_index,
                    start=False
                )
                
                # Test the stream
                test_stream.start_stream()
                test_data = test_stream.read(256, exception_on_overflow=False)
                test_stream.stop_stream()
                test_stream.close()
                
                if not test_data:
                    raise RuntimeError("Test stream returned no data")

                # Wait before opening main stream
                time.sleep(0.5)
                
                # Open main stream
                self.audio_stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    frames_per_buffer=self.frame_length,
                    input=True,
                    input_device_index=self.device_index,
                    start=False
                )
                
                self.audio_stream.start_stream()
                pico_logger.info("Audio stream initialized successfully")
                return True

            except Exception as e:
                pico_logger.error(f"Error initializing audio: {e}")
                self._force_release_audio()
                return False
                
        except Exception as e:
            pico_logger.error(f"Error in audio initialization: {e}")
            return False
        finally:
            # Clean up lock file
            try:
                os.remove(lock_file)
            except:
                pass

    def cleanup(self):
        """Enhanced cleanup"""
        pico_logger.info("Starting cleanup process...")
        
        try:
            # Clean up audio resources
            self._force_release_audio()
            
            # Clean up Porcupine
            if self.porcupine:
                try:
                    # Set timeout for delete operation
                    with time_limit(2):  # 2 second timeout
                        self.porcupine.delete()
                except Exception as e:
                    pico_logger.error(f"Error deleting Porcupine instance: {e}")
                finally:
                    self.porcupine = None

        except Exception as e:
            pico_logger.error(f"Error during cleanup: {e}")
        finally:
            # Ensure device is released
            self._force_release_audio()
            pico_logger.info("Cleanup completed")

    def _validate_audio_device(self):
        """Enhanced audio device validation"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                p = pyaudio.PyAudio()
                device_info = p.get_device_info_by_index(self.device_index)
                
                if device_info['maxInputChannels'] > 0:
                    pico_logger.info(f"Found valid input device: {device_info['name']}")
                    
                    # Test with smaller buffer
                    test_stream = p.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        input_device_index=self.device_index,
                        frames_per_buffer=256,  # Smaller buffer for test
                        start=False
                    )
                    
                    test_stream.start_stream()
                    test_data = test_stream.read(256, exception_on_overflow=False)
                    test_stream.stop_stream()
                    test_stream.close()
                    
                    if len(test_data) > 0:
                        pico_logger.info("Audio device test successful")
                        p.terminate()
                        return True
            
            except Exception as e:
                pico_logger.error(f"Audio device validation attempt {retry_count + 1} failed: {e}")
                
            finally:
                try:
                    p.terminate()
                except:
                    pass
                    
            retry_count += 1
            if retry_count < max_retries:
                self._force_release_audio()
                time.sleep(1)
                
        return False

    def initialize(self, args):
        """Initialize Porcupine and audio stream"""
        try:
            with self._lock:
                # Close any existing resources first
                # self.cleanup()
                time.sleep(0.1)  # Brief pause to ensure resources are released
                
                # Initialize Porcupine
                self.porcupine = self._create_porcupine(
                    args.access_key, 
                    args.model_path, 
                    args.keyword_paths, 
                    args.sensitivities
                )
                
                self.frame_length = self.porcupine.frame_length
                
                # Initialize audio
                if self._initialize_audio():
                    pico_logger.info("Initialization completed successfully")
                    return True
                
                raise RuntimeError("Failed to initialize audio")
            
        except Exception as e:
            pico_logger.error(f"Failed to initialize: {e}")
            self.cleanup()
            return False

    def process(self, audio_frame):
        """Process audio frame with preprocessing"""
        try:
            with self._lock:
                if self.porcupine is None or self.audio_stream is None:
                    pico_logger.warning("Components not initialized, attempting to reinitialize...")
                    if not self.initialize(self.args):
                        return -1
                    
                # Convert bytes to numpy array
                pcm_data = np.frombuffer(audio_frame, dtype=np.int16)
                
                # Apply preprocessing with gain
                processed_data = self._preprocess_audio(pcm_data)
                
                # Process with Porcupine
                if len(processed_data) >= self.frame_length:
                    try:
                        result = self.porcupine.process(processed_data[:self.frame_length])
                        return result
                    except Exception as e:
                        pico_logger.error(f"Error processing with Porcupine: {e}")
                        return -1
                return -1
            
        except Exception as e:
            pico_logger.error(f"Error processing audio frame: {e}")
            return -1

    def _preprocess_audio(self, audio_data):
        """Preprocess audio data with gain and normalization"""
        try:
            float_data = audio_data.astype(np.float32) / 32768.0
            float_data = float_data * self.gain
            float_data = np.clip(float_data, -1.0, 1.0)
            return (float_data * 32767).astype(np.int16)
        except Exception as e:
            pico_logger.error(f"Error in audio preprocessing: {e}")
            return audio_data  # Return original data if preprocessing fails

    def _create_porcupine(self, access_key, model_path, keyword_paths, sensitivities):
        """Create and return Porcupine instance with error handling"""
        try:
            return pvporcupine.create(
                access_key=access_key,
                model_path=model_path,
                keyword_paths=keyword_paths,
                sensitivities=sensitivities
            )
        except Exception as e:
            pico_logger.error(f"Failed to create Porcupine instance: {e}")
            raise