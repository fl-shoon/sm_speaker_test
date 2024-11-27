from display.setting import SettingMenu
from pico.pico import PicoVoiceTrigger
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
        self._device_initialized = False
        self.audio_player = audio_player
        self.pyaudio_instance = None
        self.audio_stream = None
        self.play_trigger = None
        self.porcupine = None
        self.server = args.server
        self.setting_menu = None
        # self.setting_menu = SettingMenu(audio_player=self.audio_player, serial_module=self.serial_module)
        self.button_check_task = None
        self.calibration_task = None
        self._cleanup_lock = asyncio.Lock()

        self.CHANNELS = CHANNELS  
        self.RATE = RATE 
        self.FORMAT = FORMAT
        self.CHUNK = 512

        try:
            self.porcupine = PicoVoiceTrigger(args)
            if self.porcupine and hasattr(self.porcupine, 'frame_length'):
                self.CHUNK = self.porcupine.frame_length
        except Exception as e:
            wakeword_logger.error(f"Failed to initialize PicoVoice: {e}")
            self.porcupine = None

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
        
    async def _cleanup_audio(self):
        """Separate audio cleanup method"""
        if self.audio_stream:
            try:
                if hasattr(self.audio_stream, 'is_active') and self.audio_stream.is_active():
                    self.audio_stream.stop_stream()
                self.audio_stream.close()
            except:
                pass
            self.audio_stream = None

        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
            except:
                pass
            self.pyaudio_instance = None

        self._device_initialized = False
        await asyncio.sleep(0.5)
        
    async def initialize_recorder(self):
        """Enhanced recorder initialization"""
        if self._device_initialized:
            return True

        if self.audio_stream is None:
            try:
                # Always clean up existing instances first
                if self.pyaudio_instance:
                    try:
                        self.pyaudio_instance.terminate()
                    except:
                        pass
                    self.pyaudio_instance = None

                time.sleep(0.5)  # Wait for cleanup

                self.pyaudio_instance = pyaudio.PyAudio()
                
                # Test the device first
                test_stream = self.pyaudio_instance.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    input=True,
                    frames_per_buffer=256,  # Smaller buffer for test
                    start=False
                )
                
                test_stream.start_stream()
                test_data = test_stream.read(256, exception_on_overflow=False)
                test_stream.stop_stream()
                test_stream.close()
                
                if not test_data:
                    raise RuntimeError("Test stream returned no data")

                time.sleep(0.5)  # Wait before opening main stream
                
                self.audio_stream = self.pyaudio_instance.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    input=True,
                    frames_per_buffer=self.CHUNK,
                    start=False
                )
                
                self.audio_stream.start_stream()
                self._device_initialized = True
                wakeword_logger.info("PyAudio recorder initialized successfully")
                return True
            except Exception as e:
                wakeword_logger.error(f"Failed to initialize PyAudio recorder: {e}")
                await self._cleanup_audio()
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
            py_recorder.calibrate_energy_threshold(frame_bytes)
            return []  
        except Exception as e:
            wakeword_logger.error(f"Error in calibration: {e}")
            return frame_bytes
        
    async def listen_for_wake_word(self, schedule_manager, py_recorder):
        tasks = set()
        try:
            if self.porcupine is None:
                wakeword_logger.error("PicoVoice not initialized - cannot listen for wake word")
                return False, WakeWordType.OTHER
            
            if self.audio_stream is None:
                self.initialize_pyaudio()
                if self.audio_stream is None:
                    wakeword_logger.error("Failed to initialize audio stream")
                    return False, WakeWordType.OTHER
                
            self.initialize_recorder()

            frame_bytes = []
            calibration_interval = 5
            last_button_check_time = time.time()
            last_calibration_time = time.time()
            button_check_interval = 1.5 # 1.5 -> check buttons every 1.5 seconds
            detections = -1

            if self.play_trigger is None:
                trigger_task = asyncio.create_task(
                    self.audio_player.play_trigger_with_logo(TriggerAudio, SeamanLogo)
                )
                tasks.add(trigger_task)
                await trigger_task
                self.play_trigger = True

            while not is_exit_event_set():
                run_pending()

                if schedule_manager and schedule_manager.check_scheduled_conversation():
                    return True, WakeWordType.SCHEDULE

                try:
                    audio_data = self.audio_stream.read(self.CHUNK, exception_on_overflow=False)
                    audio_frame = np.frombuffer(audio_data, dtype=np.int16)
                    frame_bytes.append(audio_data)

                    current_time = time.time()

                    if current_time - last_calibration_time >= calibration_interval:
                        frame_bytes = await self.calibrate_audio(py_recorder, frame_bytes)
                        last_calibration_time = current_time

                    # Process audio frame for wake word detection
                    detections = self.porcupine.process(audio_frame)
                    wake_word_triggered = detections >= 0
                    
                    if wake_word_triggered:
                        wakeword_logger.info("Wake word detected")
                        response_task = asyncio.create_task(
                            self.audio_player.play_audio(ResponseAudio)
                        )
                        tasks.add(response_task)
                        await response_task
                        return True, WakeWordType.TRIGGER
                    
                    if current_time - last_button_check_time >= button_check_interval:
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

                    await asyncio.sleep(0.01)
                except IOError as e:
                    wakeword_logger.error(f"Error reading audio stream: {e}")
                    continue
                # audio_frame = self.pv_recorder.read()
                # audio_frame_bytes = np.array(audio_frame, dtype=np.int16).tobytes()
                # frame_bytes.append(audio_frame_bytes)

                # current_time = time.time() # timestamp

                # if current_time - last_calibration_time >= calibration_interval:
                #         frame_bytes = await self.calibrate_audio(py_recorder, frame_bytes)
                #         last_calibration_time = current_time

                # detections = self.porcupine.process(audio_frame)
                # wake_word_triggered = detections >= 0
                
                # if wake_word_triggered:
                #     wakeword_logger.info("Wake word detected")
                #     response_task = asyncio.create_task(
                #         self.audio_player.play_audio(ResponseAudio)
                #     )
                #     tasks.add(response_task)
                #     await response_task
                #     return True, WakeWordType.TRIGGER
                
                # if current_time - last_button_check_time >= button_check_interval:
                #         button_task = asyncio.create_task(self.check_buttons())
                #         tasks.add(button_task)
                #         res = await button_task
                        
                #         if res == 'exit':
                #             exit_task = asyncio.create_task(
                #                 self.audio_player.play_trigger_with_logo(TriggerAudio, SeamanLogo)
                #             )
                #             tasks.add(exit_task)
                #             await exit_task
                        
                #         last_button_check_time = current_time

                await asyncio.sleep(0.01)

        except KeyboardInterrupt:
            return False, WakeWordType.OTHER
        except Exception as e:
            wakeword_logger.error(f"Error in wake word detection: {e}")
            return False, WakeWordType.OTHER
        finally:
            # Cancel all tasks first
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=1.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
            
            # Then clean up recorder with timeout
            try:
                await asyncio.wait_for(self.cleanup_recorder(), timeout=10.0)
            except asyncio.TimeoutError:
                wakeword_logger.error("Recorder cleanup timed out in listen_for_wake_word")
            except Exception as e:
                wakeword_logger.error(f"Error during recorder cleanup in listen_for_wake_word: {e}")

        return False, None
    
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

    async def cleanup_recorder(self):
        """Enhanced cleanup with proper locking and timeout"""
        try:
            async with asyncio.timeout(2.0):  # Reduced timeout
                async with self._cleanup_lock:
                    wakeword_logger.info("Starting recorder cleanup...")
                    
                    # Clean up PyAudio first
                    if self.audio_stream:
                        try:
                            if hasattr(self.audio_stream, 'is_active') and self.audio_stream.is_active():
                                self.audio_stream.stop_stream()
                            self.audio_stream.close()
                            self.audio_stream = None
                            wakeword_logger.info("Audio stream cleaned up")
                        except Exception as e:
                            wakeword_logger.error(f"Error stopping audio stream: {e}")
                        finally:
                            self.audio_stream = None

                    if self.pyaudio_instance:
                        try:
                            self.pyaudio_instance.terminate()
                            self.pyaudio_instance = None
                            wakeword_logger.info("PyAudio instance terminated")
                        except Exception as e:
                            wakeword_logger.error(f"Error terminating PyAudio: {e}")
                        finally:
                            self.pyaudio_instance = None

                    # Clean up Porcupine with very aggressive timeout
                    if self.porcupine:
                        try:
                            await asyncio.wait_for(
                                self._cleanup_porcupine(),
                                timeout=1.0
                            )
                        except (asyncio.TimeoutError, Exception) as e:
                            wakeword_logger.error(f"Forced Porcupine cleanup due to: {e}")
                            self.porcupine = None

                    wakeword_logger.info("Recorder cleanup completed")

        except asyncio.TimeoutError:
            wakeword_logger.error("Recorder cleanup timed out - forcing cleanup")
            # Force cleanup of any remaining resources
            self.audio_stream = None
            self.pyaudio_instance = None
            self.porcupine = None
        except Exception as e:
            wakeword_logger.error(f"Error during recorder cleanup: {e}")
            # Force cleanup
            self.audio_stream = None
            self.pyaudio_instance = None
            self.porcupine = None

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