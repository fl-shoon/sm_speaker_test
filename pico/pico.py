from utils.define import *

import logging
import numpy as np
import pvporcupine
import pyaudio
import time
import threading

logging.basicConfig(level=logging.INFO)
pico_logger = logging.getLogger(__name__)

class PicoVoiceTrigger:
    def __init__(self, args):
        self.porcupine = None
        self.audio = None
        self.audio_stream = None
        self.gain = args.gain if hasattr(args, 'gain') else 5.0
        self.frame_length = None
        self.device_retry_count = 3
        self.device_retry_delay = 1
        self._lock = threading.Lock()  
        self.args = args
        self.initialize(args)

    def initialize(self, args):
        """Initialize Porcupine and audio stream"""
        try:
            with self._lock:
                # Initialize Porcupine first
                if self.porcupine is None:
                    self.porcupine = self._create_porcupine(
                        args.access_key, 
                        args.model_path, 
                        args.keyword_paths, 
                        args.sensitivities
                    )
                
                self.frame_length = self.porcupine.frame_length
                
                # Initialize audio with retry logic
                for attempt in range(self.device_retry_count):
                    try:
                        if self._initialize_audio():
                            return True
                    except Exception as e:
                        pico_logger.warning(f"Audio initialization attempt {attempt + 1} failed: {e}")
                        if self.audio:
                            self.audio.terminate()
                            self.audio = None
                        time.sleep(self.device_retry_delay)
                
                raise RuntimeError("Failed to initialize audio after multiple attempts")
            
        except Exception as e:
            pico_logger.error(f"Failed to initialize: {e}")
            self.cleanup()
            return False

    def reinitialize(self):
        """Reinitialize after failure"""
        pico_logger.info("Attempting to reinitialize...")
        self.cleanup()
        time.sleep(1)  # Give ALSA time to release resources
        return self.initialize(self.args)

    def _initialize_audio(self):
        """Initialize audio subsystem"""
        try:
            if self.audio is None:
                self.audio = pyaudio.PyAudio()
            
            # Get device info
            device_index = self._find_input_device()
            device_info = self.audio.get_device_info_by_index(device_index)
            
            # Try to open the stream with different configurations
            configs_to_try = [
                # Config 1: Simple configuration
                {
                    'format': pyaudio.paInt16,
                    'channels': 1,
                    'rate': 16000,
                    'frames_per_buffer': 512,
                    'input': True,
                    'input_device_index': device_index,
                    'stream_callback': None,
                    'start': False
                }
            ]
            
            last_error = None
            for config in configs_to_try:
                try:
                    pico_logger.info(f"Trying audio configuration: {config}")
                    
                    if self.audio_stream is not None:
                        self.audio_stream.close()
                        self.audio_stream = None
                    
                    self.audio_stream = self.audio.open(**config)
                    self.audio_stream.start_stream()
                    
                    if self.audio_stream.is_active():
                        pico_logger.info("Successfully initialized audio stream")
                        return True
                        
                except Exception as e:
                    last_error = e
                    pico_logger.warning(f"Failed to initialize with config: {e}")
                    if self.audio_stream:
                        try:
                            self.audio_stream.close()
                        except:
                            pass
                        self.audio_stream = None
            
            if last_error:
                raise last_error
                
            return False
            
        except Exception as e:
            pico_logger.error(f"Error in audio initialization: {e}")
            raise

    def _find_input_device(self):
        """Find a suitable input device with enhanced error handling"""
        try:
            # Try to get the default input device first
            try:
                default_input = self.audio.get_default_input_device_info()
                pico_logger.info(f"Default input device: {default_input['name']}")
                if default_input['maxInputChannels'] > 0:
                    return default_input['index']
            except IOError:
                pico_logger.warning("Failed to get default input device")

            # Scan all devices
            for i in range(self.audio.get_device_count()):
                try:
                    device_info = self.audio.get_device_info_by_index(i)
                    if device_info['maxInputChannels'] > 0:
                        if 'USB' in device_info['name'] or 'CODEC' in device_info['name']:
                            pico_logger.info(f"Selected USB/CODEC input device: {device_info['name']}")
                            return i
                except Exception as e:
                    pico_logger.warning(f"Error checking device {i}: {e}")
                    continue

            # Fall back to first available input device
            for i in range(self.audio.get_device_count()):
                try:
                    device_info = self.audio.get_device_info_by_index(i)
                    if device_info['maxInputChannels'] > 0:
                        pico_logger.info(f"Selected fallback input device: {device_info['name']}")
                        return i
                except Exception:
                    continue

            raise RuntimeError("No suitable input device found")
        except Exception as e:
            pico_logger.error(f"Error finding input device: {e}")
            raise

    def _create_porcupine(self, access_key, model_path, keyword_paths, sensitivities):
        """Create and return Porcupine instance with error handling"""
        try:
            return pvporcupine.create(
                access_key=access_key,
                model_path=model_path,
                keyword_paths=keyword_paths,
                sensitivities=sensitivities
            )
        except pvporcupine.PorcupineInvalidArgumentError as e:
            pico_logger.error("Invalid argument provided to Porcupine: %s", e)
            raise
        except pvporcupine.PorcupineActivationError as e:
            pico_logger.error("AccessKey activation error: %s", e)
            raise
        except pvporcupine.PorcupineActivationLimitError as e:
            pico_logger.error("AccessKey has reached its temporary device limit: %s", e)
            raise
        except pvporcupine.PorcupineActivationRefusedError as e:
            pico_logger.error("AccessKey refused: %s", e)
            raise
        except pvporcupine.PorcupineActivationThrottledError as e:
            pico_logger.error("AccessKey has been throttled: %s", e)
            raise
        except pvporcupine.PorcupineError as e:
            pico_logger.error("Failed to initialize Porcupine: %s", e)
            raise
    
    def _preprocess_audio(self, audio_data):
        """Preprocess audio data with gain and normalization"""
        float_data = audio_data.astype(np.float32) / 32768.0
        float_data = float_data * self.gain
        float_data = np.clip(float_data, -1.0, 1.0)
        return (float_data * 32767).astype(np.int16)

    def process(self, audio_frame):
        """Process audio frame with preprocessing"""
        try:
            with self._lock:
                if self.porcupine is None:
                    pico_logger.warning("Porcupine instance is None, attempting to reinitialize...")
                    if not self.reinitialize():
                        return -1
                
                # Convert bytes to numpy array
                pcm_data = np.frombuffer(audio_frame, dtype=np.int16)
                
                # Apply preprocessing
                processed_data = self._preprocess_audio(pcm_data)
                
                # Process with Porcupine
                if len(processed_data) >= self.frame_length:
                    return self.porcupine.process(processed_data[:self.frame_length])
                return -1
            
        except Exception as e:
            pico_logger.error(f"Error processing audio frame: {e}")
            return -1

    def cleanup(self):
        """Cleanup resources"""
        pico_logger.info("Starting cleanup process...")
        
        with self._lock:
            if self.audio_stream is not None:
                try:
                    if self.audio_stream.is_active():
                        self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except Exception as e:
                    pico_logger.error(f"Error closing audio stream: {e}")
                self.audio_stream = None

            if self.audio is not None:
                try:
                    self.audio.terminate()
                except Exception as e:
                    pico_logger.error(f"Error terminating PyAudio: {e}")
                self.audio = None

            if self.porcupine is not None:
                try:
                    self.porcupine.delete()
                except Exception as e:
                    pico_logger.error(f"Error deleting Porcupine instance: {e}")
                self.porcupine = None

        pico_logger.info("Cleanup completed")