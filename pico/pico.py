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
        """More aggressive force release of ALSA audio device"""
        try:
            # First try a gentle cleanup
            os.system('alsactl kill rescan')
            os.system('alsactl restore')
            time.sleep(0.2)

            # Then try to remove ALSA locks
            os.system('rm -f /var/lib/alsa/asound.state.lock')
            os.system('rm -rf /var/run/alsa/runtime-*')
            time.sleep(0.2)

            # Kill any hanging audio processes
            os.system('killall -9 pulseaudio 2>/dev/null || true')
            os.system('killall -9 alsactl 2>/dev/null || true')
            os.system('fuser -k -9 /dev/snd/* 2>/dev/null || true')
            time.sleep(0.5)

            # Reload ALSA subsystem
            os.system('alsa force-reload 2>/dev/null || true')
            time.sleep(1.0)

            # Final restore
            os.system('alsactl restore')
            time.sleep(0.5)
            
        except Exception as e:
            pico_logger.error(f"Error during audio device release: {e}")

    def _initialize_audio(self):
        """Initialize audio with extra precautions"""
        try:
            # Always force release first
            self._force_release_audio()
            
            if not self._validate_audio_device():
                pico_logger.error("Audio device validation failed")
                return False

            # Close any existing PyAudio instance
            if self.audio:
                try:
                    if self.audio_stream:
                        self.audio_stream.stop_stream()
                        self.audio_stream.close()
                    self.audio.terminate()
                except:
                    pass
                self.audio = None
                self.audio_stream = None
                time.sleep(0.5)

            # Create new PyAudio instance
            self.audio = pyaudio.PyAudio()
            
            # Get device info
            device_info = self.audio.get_device_info_by_index(self.device_index)
            pico_logger.info(f"Using audio device: {device_info['name']}")
            
            # Open stream with minimal buffer size first
            test_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                frames_per_buffer=256,  # Start with small buffer
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
                
            # If test successful, open actual stream
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
            pico_logger.error(f"Error in audio initialization: {e}")
            self._force_release_audio()
            return False

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

    def cleanup(self):
        """Cleanup resources"""
        pico_logger.info("Starting cleanup process...")
        
        try:
            # Clean up in reverse order of initialization
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

            # Handle Porcupine cleanup separately
            if self.porcupine is not None:
                try:
                    # Add a timeout for delete operation
                    signal.alarm(2)  # Set 2 second alarm
                    self.porcupine.delete()
                    signal.alarm(0)  # Disable alarm
                except Exception as e:
                    pico_logger.error(f"Error deleting Porcupine instance: {e}")
                finally:
                    self.porcupine = None
                    signal.alarm(0)  # Ensure alarm is disabled

        except Exception as e:
            pico_logger.error(f"Error during PicoVoice cleanup: {e}")
        finally:
            # Ensure everything is set to None
            self.audio_stream = None
            self.audio = None
            self.porcupine = None
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