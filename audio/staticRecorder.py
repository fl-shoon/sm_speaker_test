import pyaudio
import numpy as np
import logging
from queue import Queue, Full
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PvRecorder:
    """Optimized drop-in replacement for PvRecorder using PyAudio."""
    
    def __init__(self, device_index=-1, frame_length=512):
        self._frame_length = frame_length
        self._audio = pyaudio.PyAudio()
        self._device_index = self._find_input_device(device_index)
        self._stream = None
        self._is_recording = False
        # Increase queue size and add overflow counter
        self._audio_queue = Queue(maxsize=1000)
        self._overflow_count = 0
        self._last_overflow_log = 0
        self._overflow_log_interval = 5  # Log overflow every 5 seconds
        
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
        """Optimized callback for audio stream."""
        if self._is_recording:
            try:
                self._audio_queue.put_nowait(in_data)
            except Full:
                self._overflow_count += 1
                current_time = time.time()
                if current_time - self._last_overflow_log >= self._overflow_log_interval:
                    logger.warning(f"Buffer overflow count: {self._overflow_count}")
                    self._last_overflow_log = current_time
                    
                # Clear half of the queue when overflow occurs
                try:
                    for _ in range(self._audio_queue.qsize() // 2):
                        self._audio_queue.get_nowait()
                except Exception:
                    pass
        return (None, pyaudio.paContinue)
    
    def start(self):
        """Start recording with optimized buffer settings."""
        if self._stream is not None:
            return
            
        try:
            # Optimize buffer size to reduce overflows
            buffer_size = 2 * self._frame_length  # Double buffer size
            
            self._stream = self._audio.open(
                rate=self._sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                input_device_index=self._device_index,
                frames_per_buffer=buffer_size,
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
        """Optimized read method with better error handling."""
        if not self._is_recording:
            raise RuntimeError("Recording not started")
            
        try:
            # Reduced timeout to prevent blocking
            data = self._audio_queue.get(timeout=0.1)
            return np.frombuffer(data, dtype=np.int16)
        except Exception as e:
            if not isinstance(e, Full):  # Don't log timeout exceptions
                logger.error(f"Error reading audio frame: {e}")
            return np.zeros(self._frame_length, dtype=np.int16)
    
    def stop(self):
        """Stop recording and clean up buffers."""
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
        self._clear_queue()
    
    def _clear_queue(self):
        """Clear the audio queue efficiently."""
        try:
            while True:
                self._audio_queue.get_nowait()
        except:
            pass
    
    def delete(self):
        """Clean up all resources."""
        self.stop()
        if self._audio is not None:
            try:
                self._audio.terminate()
            except Exception as e:
                logger.error(f"Error terminating audio: {e}")
            finally:
                self._audio = None
                
    @property
    def is_recording(self):
        """Check if recording is active."""
        return self._is_recording and self._stream is not None