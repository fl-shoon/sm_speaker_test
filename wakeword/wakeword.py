from display.setting import SettingMenu
from openai import OpenAI
from utils.define import *
from utils.scheduler import run_pending
from utils.utils import is_exit_event_set

import asyncio
import logging
import numpy as np
import pyaudio
import time

logging.basicConfig(level=logging.INFO)
wakeword_logger = logging.getLogger(__name__)

class WakeWord:
    def __init__(self, args, audio_player):
        self.audio_player = audio_player
        self.pyaudio_instance = None
        self.audio_stream = None
        self.play_trigger = None
        self.server = args.server
        self._cleanup_lock = asyncio.Lock()
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        
        # Audio settings
        self.CHANNELS = 1
        self.RATE = 16000
        self.FORMAT = pyaudio.paInt16
        self.CHUNK = 1024 * 2  # 2048 samples = ~128ms at 16kHz
        self.RECORD_SECONDS = 2  # Process 2 seconds of audio at a time
        
        # Wake word settings
        self.WAKE_WORDS = ["こんにちは", "聞いて", "お願い"]
        
        self.initialize_pyaudio()

    def initialize_pyaudio(self):
        try:
            if self.pyaudio_instance is None:
                self.pyaudio_instance = pyaudio.PyAudio()
            
            if self.audio_stream is None:
                self.audio_stream = self.pyaudio_instance.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    input=True,
                    frames_per_buffer=self.CHUNK
                )
                wakeword_logger.info("PyAudio recorder initialized successfully")
        except Exception as e:
            wakeword_logger.error(f"Failed to initialize PyAudio recorder: {e}")
            if self.pyaudio_instance:
                try:
                    self.pyaudio_instance.terminate()
                except:
                    pass
                self.pyaudio_instance = None

    async def check_for_wake_word(self, audio_frames):
        """Check audio for wake word using OpenAI Whisper"""
        try:
            # Save audio frames to temporary file
            temp_file = "/tmp/wake_check.wav"
            self.save_audio(audio_frames, temp_file)
            
            # Transcribe with Whisper
            with open(temp_file, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ja",
                    temperature=0.0,
                    prompt="「こんにちは」「聞いて」「お願い」などの呼びかけの言葉を検出してください。"
                )
            
            # Check if any wake word is in the transcription
            transcribed_text = transcript.text.strip().lower()
            # wakeword_logger.info(f"Transcribed: {transcribed_text}")
            
            for wake_word in self.WAKE_WORDS:
                if wake_word in transcribed_text:
                    wakeword_logger.info(f"Wake word detected: {wake_word}")
                    return True
            
            return False
            
        except KeyboardInterrupt:
            wakeword_logger.info("KeyboardInterrupt received in check_for_wake_word")
            raise
        except Exception as e:
            wakeword_logger.error(f"Error checking for wake word: {e}")
            return False
        finally:
            try:
                os.remove(temp_file)
            except:
                pass

    def save_audio(self, frames, filename):
        """Save audio frames to WAV file"""
        try:
            wf = wave.open(filename, 'wb')
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.pyaudio_instance.get_sample_size(self.FORMAT))
            wf.setframerate(self.RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
        except Exception as e:
            wakeword_logger.error(f"Error saving audio: {e}")
            raise
    
    def initialize_recorder(self):
        if self.audio_stream is None:
            try:
                if self.pyaudio_instance is None:
                    self.pyaudio_instance = pyaudio.PyAudio()
                
                self.audio_stream = self.pyaudio_instance.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    input=True,
                    frames_per_buffer=self.CHUNK
                )
                wakeword_logger.info("PyAudio recorder initialized successfully")
            except Exception as e:
                wakeword_logger.error(f"Failed to initialize PyAudio recorder: {e}")
                raise
    
    async def check_buttons(self):
        try:
            active_buttons = await self.server.get_buttons()
            if active_buttons[4]: # RIGHT button
                wakeword_logger.info("Right Button Pressed")
                # response = self.setting_menu.display_menu()
                # if response:
                #     return response
                await asyncio.sleep(0.2)
            return None
        except Exception as e:
            wakeword_logger.error(f"Error in check_buttons: {e}")
            return None
        
    async def calibrate_audio(self, py_recorder, frame_bytes):
        try:
            if is_exit_event_set():
                raise KeyboardInterrupt
                
            py_recorder.calibrate_energy_threshold(frame_bytes)
            return []
        except KeyboardInterrupt:
            wakeword_logger.info("Calibration interrupted")
            raise
        except Exception as e:
            wakeword_logger.error(f"Error in calibration: {e}")
            return frame_bytes
        
    async def _cleanup_porcupine(self):
        """Separate method for Porcupine cleanup to handle timeouts"""
        if self.porcupine:
            try:
                # Create a process to handle Porcupine cleanup
                def cleanup_in_process():
                    try:
                        if hasattr(self.porcupine, 'cleanup'):
                            self.porcupine.cleanup()
                        return True
                    except Exception:
                        return False

                loop = asyncio.get_event_loop()
                # Run cleanup in executor with very short timeout
                await asyncio.wait_for(
                    loop.run_in_executor(None, cleanup_in_process),
                    timeout=1.0
                )
                wakeword_logger.info("Porcupine cleanup completed")
            except asyncio.TimeoutError:
                wakeword_logger.error("Porcupine cleanup timed out - forcing cleanup")
                self.porcupine = None  # Force cleanup by dropping reference
            except Exception as e:
                wakeword_logger.error(f"Error in Porcupine cleanup: {e}")
                self.porcupine = None  # Force cleanup by dropping reference
            finally:
                self.porcupine = None

    async def listen_for_wake_word(self, schedule_manager, py_recorder):
        tasks = set()
        try:
            if self.audio_stream is None:
                self.initialize_pyaudio()
                if self.audio_stream is None:
                    wakeword_logger.error("Failed to initialize audio stream")
                    return False, WakeWordType.OTHER

            frames = []
            frame_bytes = []
            calibration_interval = 5
            last_button_check_time = time.time()
            last_calibration_time = time.time()
            button_check_interval = 1.5
            chunks_per_check = int(self.RECORD_SECONDS * self.RATE / self.CHUNK)
            
            # if self.play_trigger is None:
            #     if self.audio_stream:
            #         self.audio_stream.stop_stream()

            #     trigger_task = asyncio.create_task(
            #         self.audio_player.play_trigger_with_logo(TriggerAudio, SeamanLogo)
            #     )
            #     tasks.add(trigger_task)
            #     await trigger_task
            #     self.play_trigger = True

            #     if self.audio_stream:
            #         self.audio_stream.start_stream()
            if self.play_trigger is None:
                try:
                    if self.audio_stream:
                        self.audio_stream.stop_stream()
                    await asyncio.sleep(0.1)  

                    trigger_task = asyncio.create_task(
                        self.audio_player.play_trigger_with_logo(TriggerAudio, SeamanLogo)
                    )
                    tasks.add(trigger_task)
                    await trigger_task
                    self.play_trigger = True
                    await asyncio.sleep(0.1)  # Wait before restarting stream

                    if self.audio_stream:
                        self.audio_stream.start_stream()
                except Exception as e:
                    wakeword_logger.error(f"Error playing trigger sound: {e}")

            while not is_exit_event_set():
                try:
                    run_pending()

                    if schedule_manager and schedule_manager.check_scheduled_conversation():
                        return True, WakeWordType.SCHEDULE
                    
                    frames = []
                    # Record audio chunks
                    # for _ in range(chunks_per_check):
                    #     data = self.audio_stream.read(self.CHUNK, exception_on_overflow=False)
                    #     frames.append(data)
                    #     frame_bytes.append(data)
                    for _ in range(chunks_per_check):
                        if is_exit_event_set():
                            raise KeyboardInterrupt
                        data = self.audio_stream.read(self.CHUNK, exception_on_overflow=False)
                        frames.append(data)
                        frame_bytes.append(data)

                    # Calibrate periodically
                    current_time = time.time()
                    
                    if current_time - last_calibration_time >= calibration_interval:
                        try:
                            if self.audio_stream:
                                self.audio_stream.stop_stream()
                            
                            frame_bytes = await self.calibrate_audio(py_recorder, frame_bytes)
                            last_calibration_time = current_time

                            if self.audio_stream:
                                self.audio_stream.start_stream()
                        except KeyboardInterrupt:
                            raise 
                        except Exception as e:
                            wakeword_logger.error(f"Error in calibration: {e}")
                    
                    # Check buttons periodically
                    if current_time - last_button_check_time >= button_check_interval:
                        try:
                            button_task = asyncio.create_task(self.check_buttons())
                            tasks.add(button_task)
                            res = await button_task
                            
                            if res == 'exit':
                                exit_task = asyncio.create_task(
                                    self.audio_player.play_trigger_with_logo(TriggerAudio, SeamanLogo)
                                )
                                tasks.add(exit_task)
                                await exit_task
                            
                            last_button_check_time = current_time
                        except KeyboardInterrupt:
                            raise
                        except Exception as e:
                            wakeword_logger.error(f"Error checking buttons: {e}")

                    if is_exit_event_set():
                        raise KeyboardInterrupt
                    
                    # Check for wake word
                    if await self.check_for_wake_word(frames):
                        try:
                            if self.audio_stream:
                                self.audio_stream.stop_stream()
                            await asyncio.sleep(0.1)

                            # response_task = asyncio.create_task(
                            #     self.audio_player.play_audio(ResponseAudio)
                            # )
                            # tasks.add(response_task)
                            # await asyncio.wait_for(response_task, timeout=2.0)
                            for attempt in range(3):
                                try:
                                    response_task = asyncio.create_task(
                                        self.audio_player.play_audio(ResponseAudio)
                                    )
                                    tasks.add(response_task)
                                    await asyncio.wait_for(response_task, timeout=2.0)
                                    break
                                except Exception as e:
                                    wakeword_logger.error(f"Attempt {attempt + 1} to play response failed: {e}")
                                    if attempt < 2:  
                                        await asyncio.sleep(0.1)

                            await asyncio.sleep(0.1)
                            
                            return True, WakeWordType.TRIGGER
                        except asyncio.TimeoutError:
                            wakeword_logger.error("Response audio playback timed out")
                        except Exception as e:
                            wakeword_logger.error(f"Error playing response audio: {e}")
                        finally:
                            if self.audio_stream:
                                self.audio_stream.start_stream()

                    frames = []
                    await asyncio.sleep(0.1)

                except IOError as e:
                    wakeword_logger.error(f"Error reading audio stream: {e}")
                    await asyncio.sleep(0.1)
                    continue
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    wakeword_logger.error(f"Error in wake word main loop: {e}")
                    await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            wakeword_logger.info("KeyboardInterrupt received in listen_for_wake_word")
            return False, WakeWordType.OTHER
        except Exception as e:
            wakeword_logger.error(f"Error in wake word detection: {e}")
            return False, WakeWordType.OTHER
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=1.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
            
            await self.cleanup_recorder()

        return False, None

    async def cleanup_recorder(self):
        """Enhanced cleanup with proper locking"""
        async with self._cleanup_lock:
            if self.audio_stream:
                try:
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()
                    self.audio_stream = None
                except Exception as e:
                    wakeword_logger.error(f"Error stopping audio stream: {e}")

            if self.pyaudio_instance:
                try:
                    self.pyaudio_instance.terminate()
                    self.pyaudio_instance = None
                except Exception as e:
                    wakeword_logger.error(f"Error terminating PyAudio: {e}")

    def __del__(self):
        """Enhanced destructor with proper cleanup"""
        if self.audio_stream or self.pyaudio_instance:
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(self.cleanup_recorder())
            else:
                # Synchronous cleanup as fallback
                if self.audio_stream:
                    try:
                        self.audio_stream.stop_stream()
                        self.audio_stream.close()
                    except:
                        pass
                if self.pyaudio_instance:
                    try:
                        self.pyaudio_instance.terminate()
                    except:
                        pass