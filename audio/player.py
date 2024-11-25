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
        self.mixer_initialized = False
        
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
        os.environ['SDL_AUDIODRIVER'] = 'pulseaudio'  
        
        try:
            with suppress_stdout_stderr():
                pygame.init()
                mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
                
            self.current_volume = 0.5
            mixer.music.set_volume(self.current_volume)
            self.audio_available = True
            self.mixer_initialized = True
            
        except Exception as e:
            print(f"Warning: Audio initialization failed with pulseaudio: {e}")
            try:
                os.environ['SDL_AUDIODRIVER'] = 'alsa'
                with suppress_stdout_stderr():
                    mixer.quit()
                    mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
                self.current_volume = 0.5
                mixer.music.set_volume(self.current_volume)
                self.audio_available = True
                self.mixer_initialized = True
            except Exception as e2:
                print(f"Warning: Audio initialization failed with alsa: {e2}")
                print("Audio playback will be disabled")
                self.audio_available = False
                self.mixer_initialized = False

    def set_audio_volume(self, volume):
        """Set audio volume between 0.0 and 1.0"""
        if not self.mixer_initialized:
            return
        self.current_volume = max(0.0, min(1.0, volume))
        if mixer.music.get_busy():
            mixer.music.set_volume(self.current_volume)

    def play_audio(self, filename):
        """Play audio if available"""
        if not self.audio_available or not self.mixer_initialized:
            print("Audio playback is not available")
            return
        try:
            with suppress_stdout_stderr():
                mixer.music.load(filename)
                mixer.music.play()
                mixer.music.set_volume(self.current_volume)
        except Exception as e:
            print(f"Error playing audio: {e}")
            self.audio_available = False

    async def check_music_status(self):
        """Check if music is still playing"""
        if not self.mixer_initialized:
            await asyncio.sleep(2)  
            self.playback_active = False
            return
            
        try:
            while self.playback_active and mixer.music.get_busy():
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error checking music status: {e}")
        finally:
            self.playback_active = False

    async def play_trigger_with_logo(self, trigger_audio, logo_path):
        try: 
            self.playback_active = True
            if self.audio_available and self.mixer_initialized:
                self.play_audio(trigger_audio)
                audio_task = asyncio.create_task(self.check_music_status())
            else:
                audio_task = asyncio.create_task(asyncio.sleep(2))  
            
            logo_task = asyncio.create_task(self.display.fade_in_logo(logo_path))
            await asyncio.gather(audio_task, logo_task)
        except Exception as e:
            print(f"Error in play_trigger_with_logo: {e}")
        finally:
            self.playback_active = False

    async def sync_audio_and_gif(self, audio_file, gif_path):
        try:
            if self.mixer_initialized:
                self.set_audio_volume(0.3)
            self.playback_active = True
            
            if self.audio_available and self.mixer_initialized:
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
        if self.mixer_initialized and self.audio_available:
            try:
                mixer.music.stop()
            except Exception as e:
                print(f"Error stopping playback: {e}")
                self.audio_available = False