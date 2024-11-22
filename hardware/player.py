from contextlib import contextmanager
from pygame import mixer

import asyncio
import os
import pygame
import sys

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
        
        # Set environment variables
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
        os.environ['SDL_AUDIODRIVER'] = 'default'
        
        try:
            with suppress_stdout_stderr():
                pygame.init()
                mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
                
            # Test audio
            self.current_volume = 0.5
            mixer.music.set_volume(self.current_volume)
            self.audio_available = True
            
        except Exception as e:
            print(f"Warning: Audio initialization failed: {e}")
            print("Audio playback will be disabled")
            self.audio_available = False

    def set_audio_volume(self, volume):
        """Set audio volume between 0.0 and 1.0"""
        self.current_volume = max(0.0, min(1.0, volume))
        if mixer.music.get_busy():
            mixer.music.set_volume(self.current_volume)

    def play_audio(self, filename):
        """Play audio if available"""
        if not self.audio_available:
            print("Audio playback is not available")
            return
        try:
            with suppress_stdout_stderr():
                mixer.music.load(filename)
                mixer.music.play()
                mixer.music.set_volume(self.current_volume)
        except Exception as e:
            print(f"Error playing audio: {e}")

    async def check_music_status(self):
        """Check if music is still playing"""
        while self.playback_active and mixer.music.get_busy():
            await asyncio.sleep(0.1)
        self.playback_active = False

    async def play_trigger_with_logo(self, trigger_audio, logo_path):
        try: 
            self.playback_active = True
            if self.audio_available:
                self.play_audio(trigger_audio)
                audio_task = asyncio.create_task(self.check_music_status())
            else:
                audio_task = asyncio.create_task(asyncio.sleep(2))  # Fallback delay
            
            logo_task = asyncio.create_task(self.display.fade_in_logo(logo_path))
            await asyncio.gather(audio_task, logo_task)
        except Exception as e:
            print(f"Error in play_trigger_with_logo: {e}")
        finally:
            self.playback_active = False

    async def sync_audio_and_gif(self, audio_file, gif_path):
        try:
            self.playback_active = True
            if self.audio_available:
                self.play_audio(audio_file)
                audio_task = asyncio.create_task(self.check_music_status())
            else:
                audio_task = asyncio.create_task(asyncio.sleep(5))  # Fallback delay
            
            gif_task = asyncio.create_task(self.display.update_gif(gif_path))
            await asyncio.gather(audio_task, gif_task)
        except Exception as e:
            print(f"Error in sync_audio_and_gif: {e}")
        finally:
            self.playback_active = False
            await self.display.send_white_frames()

    def stop_playback(self):
        """Stop current audio and animation playback"""
        self.playback_active = False
        mixer.music.stop()