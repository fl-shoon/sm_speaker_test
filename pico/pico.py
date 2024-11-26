from utils.define import *

import logging
import numpy as np
import pvporcupine
import pyaudio

logging.basicConfig(level=logging.INFO)
pico_logger = logging.getLogger(__name__)

class PicoVoiceTrigger:
    def __init__(self, args):
        self.porcupine = None
        self.audio = None
        self.audio_stream = None
        self.gain = args.gain if hasattr(args, 'gain') else 5.0
        self.frame_length = None  # Will be set after Porcupine initialization
        self.initialize(args)

    def initialize(self, args):
        """Initialize Porcupine and audio stream"""
        try:
            # Initialize Porcupine first to get frame_length
            self.porcupine = self._create_porcupine(
                args.access_key, 
                args.model_path, 
                args.keyword_paths, 
                args.sensitivities
            )
            
            # Set frame_length after Porcupine initialization
            self.frame_length = self.porcupine.frame_length
            
            # Initialize audio
            self.audio = pyaudio.PyAudio()
            
            # Find suitable input device and setup audio stream
            device_index = self._find_input_device()
            device_info = self.audio.get_device_info_by_index(device_index)
            
            # Use a larger buffer size
            buffer_size = self.frame_length * 2
            
            self.audio_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.porcupine.sample_rate,
                input=True,
                frames_per_buffer=buffer_size,
                input_device_index=device_index,
                stream_callback=None,
                start=False
            )
            
            self.audio_stream.start_stream()
            pico_logger.info(f"Audio stream initialized and started")
            return True
            
        except Exception as e:
            pico_logger.error(f"Failed to initialize: {e}")
            self.cleanup()
            return False

    def _find_input_device(self):
        """Find a suitable input device"""
        try:
            default_input = self.audio.get_default_input_device_info()
            pico_logger.info(f"Default input device: {default_input['name']}")
            
            # Find the first available input device
            for i in range(self.audio.get_device_count()):
                try:
                    device_info = self.audio.get_device_info_by_index(i)
                    if device_info['maxInputChannels'] > 0:
                        pico_logger.info(f"Selected input device: {device_info['name']}")
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