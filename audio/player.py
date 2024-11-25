from contextlib import contextmanager

import asyncio
import os
import pyaudio
import sys
import wave

@contextmanager
def suppress_stdout_stderr():
    """A context manager that redirects stdout and stderr to devnull"""
    _stdout = sys.stdout
    _stderr = sys.stderr
    null = open(os.devnull, 'w')
    try:
        sys.stdout = null
        sys.stderr = null
        yield
    finally:
        sys.stdout = _stdout
        sys.stderr = _stderr
        null.close()

class AudioPlayer:
    def __init__(self, display):
        self.display = display
        self.display.set_player_for_display(self)  
        self.playback_active = False
        self.audio_available = False
        self.current_volume = 0.5
        self.current_stream = None
        self.pyaudio_instance = None
        self._cleanup_lock = asyncio.Lock()
        
        try:
            with suppress_stdout_stderr():
                self.pyaudio_instance = pyaudio.PyAudio()
            self.audio_available = True
        except Exception as e:
            print(f"Warning: Audio initialization failed: {e}")
            print("Audio playback will be disabled")
            self.audio_available = False

    def set_audio_volume(self, volume):
        """Set audio volume between 0.0 and 1.0"""
        self.current_volume = max(0.0, min(1.0, volume))

    async def play_audio(self, filename):
        """Play audio if available"""
        if not self.audio_available:
            print("Audio playback is not available")
            return
        
        try:
            wf = wave.open(filename, "rb")
            
            # Create stream
            stream = self.pyaudio_instance.open(
                format=self.pyaudio_instance.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True,
            )
            self.current_stream = stream

            # Play audio in chunks
            chunk_size = 1024
            data = wf.readframes(chunk_size)

            while data and self.playback_active:
                # Apply volume adjustment
                if self.current_volume != 1.0:
                    # Convert bytes to array of integers
                    import array
                    data_array = array.array('h', data)
                    # Apply volume
                    data_array = array.array('h', 
                        (int(x * self.current_volume) for x in data_array))
                    # Convert back to bytes
                    data = data_array.tobytes()
                
                stream.write(data)
                data = wf.readframes(chunk_size)
                await asyncio.sleep(0.01)

            # Cleanup
            stream.stop_stream()
            stream.close()
            self.current_stream = None
            wf.close()
            
        except Exception as e:
            print(f"Error playing audio: {e}")
            self.audio_available = False

    async def check_music_status(self):
        """Check if audio is still playing"""
        if not self.audio_available:
            await asyncio.sleep(2)
            self.playback_active = False
            return
            
        try:
            while self.playback_active and self.current_stream:
                if not self.current_stream.is_active():
                    break
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error checking audio status: {e}")
        finally:
            self.playback_active = False

    async def play_trigger_with_logo(self, trigger_audio, logo_path):
        try:
            self.playback_active = True
            if self.audio_available:
                audio_task = asyncio.create_task(self.play_audio(trigger_audio))
                status_task = asyncio.create_task(self.check_music_status())
            else:
                audio_task = asyncio.create_task(asyncio.sleep(2))
                status_task = audio_task
            
            logo_task = asyncio.create_task(self.display.fade_in_logo(logo_path))
            await asyncio.gather(audio_task, status_task, logo_task)
        except Exception as e:
            print(f"Error in play_trigger_with_logo: {e}")
        finally:
            self.playback_active = False

    async def sync_audio_and_gif(self, audio_file, gif_path):
        try:
            self.set_audio_volume(0.3)
            self.playback_active = True
            
            if self.audio_available:
                audio_task = asyncio.create_task(self.play_audio(audio_file))
                status_task = asyncio.create_task(self.check_music_status())
            else:
                audio_task = asyncio.create_task(asyncio.sleep(5))
                status_task = audio_task
            
            gif_task = asyncio.create_task(self.display.update_gif(gif_path))
            await asyncio.gather(audio_task, status_task, gif_task)
        except Exception as e:
            print(f"Error in sync_audio_and_gif: {e}")
        finally:
            self.playback_active = False
            await self.display.send_white_frames()

    def stop_playback(self):
        """Stop current audio playback"""
        self.playback_active = False
        if self.current_stream and self.audio_available:
            try:
                self.current_stream.stop_stream()
                self.current_stream.close()
                self.current_stream = None
            except Exception as e:
                print(f"Error stopping playback: {e}")
                self.audio_available = False

    async def cleanup(self):
        """Async cleanup method"""
        async with self._cleanup_lock:
            if self.current_stream:
                try:
                    self.current_stream.stop_stream()
                    self.current_stream.close()
                    self.current_stream = None
                except Exception as e:
                    print(f"Error closing stream: {e}")
            
            if self.pyaudio_instance:
                try:
                    self.pyaudio_instance.terminate()
                    self.pyaudio_instance = None
                except Exception as e:
                    print(f"Error terminating PyAudio: {e}")

    def __del__(self):
        """Ensure cleanup runs"""
        if self.current_stream or self.pyaudio_instance:
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(self.cleanup())
            else:
                # Synchronous cleanup as fallback
                if self.current_stream:
                    self.current_stream.stop_stream()
                    self.current_stream.close()
                if self.pyaudio_instance:
                    self.pyaudio_instance.terminate()