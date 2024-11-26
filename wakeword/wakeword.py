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
        self.audio_player = audio_player
        self.pyaudio_instance = None
        self.audio_stream = None
        # self.pv_recorder = None 
        self.play_trigger = None
        self.porcupine = PicoVoiceTrigger(args)
        self.server = args.server
        self.setting_menu = None
        # self.setting_menu = SettingMenu(audio_player=self.audio_player, serial_module=self.serial_module)
        self.button_check_task = None
        self.calibration_task = None
        self.initialize_pyaudio()
        self._cleanup_lock = asyncio.Lock()

    def initialize_pyaudio(self):
        # PyAudio configuration
        self.CHANNELS = 1  
        self.RATE = 16000 
        self.FORMAT = pyaudio.paInt16
        self.CHUNK = self.porcupine.frame_length
        
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
    
    # def initialize_recorder(self):
    #     if self.pv_recorder is None:
    #         try:
    #             self.pv_recorder = PvRecorder(frame_length=self.porcupine.frame_length)
    #         except Exception as e:
    #             wakeword_logger.error(f"Failed to initialize recorder: {e}")
    #             raise

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
            self.initialize_recorder()
            # self.pv_recorder.start()

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
            raise
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
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

            if self.porcupine:
                try:
                    self.porcupine.cleanup()
                except Exception as e:
                    wakeword_logger.error(f"Error terminating PicoVoice: {e}")

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