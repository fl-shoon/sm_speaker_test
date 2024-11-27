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
        self._lock = threading.Lock()
        self.args = args
        self.device_index = 0  # Fixed device index for USB CODEC
        self.initialize(args)

    def initialize(self, args):
        """Initialize Porcupine and audio stream"""
        try:
            with self._lock:
                # Close any existing resources first
                self.cleanup()
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

    def _initialize_audio(self):
        """Initialize audio subsystem"""
        try:
            # Create new PyAudio instance
            if self.audio is None:
                self.audio = pyaudio.PyAudio()
            
            # Get device info
            device_info = self.audio.get_device_info_by_index(self.device_index)
            pico_logger.info(f"Using audio device: {device_info['name']}")
            
            # Close any existing stream
            if self.audio_stream is not None:
                try:
                    if self.audio_stream.is_active():
                        self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except:
                    pass
                self.audio_stream = None
            
            # Open new stream with optimized settings
            self.audio_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                frames_per_buffer=self.frame_length,
                input=True,
                input_device_index=self.device_index,
                start=False
            )
            
            # Test read before starting stream
            try:
                self.audio_stream.start_stream()
                test_data = self.audio_stream.read(self.frame_length, exception_on_overflow=False)
                if not test_data:
                    raise RuntimeError("Failed to read test data")
            except Exception as e:
                pico_logger.error(f"Stream test failed: {e}")
                if self.audio_stream:
                    self.audio_stream.close()
                    self.audio_stream = None
                raise
            
            pico_logger.info("Audio stream initialized successfully")
            return True
            
        except Exception as e:
            pico_logger.error(f"Error in audio initialization: {e}")
            if self.audio_stream:
                try:
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
                finally:
                    self.audio_stream = None

            if self.audio is not None:
                try:
                    self.audio.terminate()
                except Exception as e:
                    pico_logger.error(f"Error terminating PyAudio: {e}")
                finally:
                    self.audio = None

            if self.porcupine is not None:
                try:
                    self.porcupine.delete()
                except Exception as e:
                    pico_logger.error(f"Error deleting Porcupine instance: {e}")
                finally:
                    self.porcupine = None

            # Small delay to ensure resources are released
            time.sleep(0.1)

        pico_logger.info("Cleanup completed")

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