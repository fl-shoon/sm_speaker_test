import pyaudio
import numpy as np
import logging
from queue import Queue
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PvRecorder:
    """Drop-in replacement for PvRecorder using PyAudio."""
    
    def __init__(self, device_index=-1, frame_length=512):
        self._frame_length = frame_length
        self._audio = pyaudio.PyAudio()
        self._device_index = self._find_input_device(device_index)
        self._stream = None
        self._is_recording = False
        self._audio_queue = Queue(maxsize=100)
        
        # Standard parameters for wake word detection
        self._sample_rate = 16000
        
        logger.info(f"Initialized recorder with device {self._device_index}")
        
    def _find_input_device(self, preferred_index):
        """Find a suitable input device."""
        if preferred_index >= 0:
            try:
                device_info = self._audio.get_device_info_by_index(preferred_index)
                if device_info['maxInputChannels'] > 0:
                    return preferred_index
            except Exception:
                pass
        
        # Search for any working input device
        for i in range(self._audio.get_device_count()):
            try:
                device_info = self._audio.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    logger.info(f"Selected input device: {device_info['name']}")
                    return i
            except Exception:
                continue
                
        raise RuntimeError("No suitable audio input device found")
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream."""
        if self._is_recording:
            try:
                self._audio_queue.put_nowait(in_data)
            except Exception as e:
                logger.warning(f"Buffer overflow: {e}")
        return (None, pyaudio.paContinue)
    
    def start(self):
        """Start recording."""
        if self._stream is not None:
            return
            
        try:
            self._stream = self._audio.open(
                rate=self._sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                input_device_index=self._device_index,
                frames_per_buffer=self._frame_length,
                stream_callback=self._audio_callback
            )
            
            self._is_recording = True
            self._stream.start_stream()
            logger.info("Recording started")
            
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.cleanup()
            raise
    
    def read(self):
        """Read a frame of audio data."""
        if not self._is_recording:
            raise RuntimeError("Recording not started")
            
        try:
            data = self._audio_queue.get(timeout=1.0)
            return np.frombuffer(data, dtype=np.int16)
        except Exception as e:
            logger.error(f"Error reading audio frame: {e}")
            return np.zeros(self._frame_length, dtype=np.int16)
    
    def stop(self):
        """Stop recording."""
        self._is_recording = False
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")
            finally:
                self._stream = None
                
        # Clear the audio queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except:
                pass
    
    def delete(self):
        """Clean up resources."""
        self.stop()
        if self._audio is not None:
            try:
                self._audio.terminate()
            except Exception as e:
                logger.error(f"Error terminating audio: {e}")
            finally:
                self._audio = None