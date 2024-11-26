from display.setting import SettingMenu
from pico.pico import PicoVoiceTrigger
from utils.define import *
from utils.scheduler import run_pending
from utils.utils import is_exit_event_set
from pvrecorder import PvRecorder
import logging
import numpy as np
import time
import asyncio
import subprocess

logging.basicConfig(level=logging.INFO)
wakeword_logger = logging.getLogger(__name__)

class WakeWord:
    def __init__(self, args, audio_player):
        self.audio_player = audio_player
        self.pv_recorder = None 
        self.play_trigger = None
        self.porcupine = PicoVoiceTrigger(args)
        self.server = args.server
        self.setting_menu = None
        self.button_check_task = None
        self.calibration_task = None
        self._init_retries = 3
        self._retry_delay = 2
        
    async def _release_audio_device(self):
        """Release any processes holding the audio device."""
        try:
            # Kill any processes using the sound device
            subprocess.run(['fuser', '-k', '/dev/snd/*'], 
                         stderr=subprocess.DEVNULL, 
                         stdout=subprocess.DEVNULL)
            await asyncio.sleep(1)  # Wait for cleanup
            
            # Optionally reload sound modules
            subprocess.run(['rmmod', 'snd_usb_audio'], 
                         stderr=subprocess.DEVNULL, 
                         stdout=subprocess.DEVNULL)
            await asyncio.sleep(0.5)
            subprocess.run(['modprobe', 'snd_usb_audio'], 
                         stderr=subprocess.DEVNULL, 
                         stdout=subprocess.DEVNULL)
            await asyncio.sleep(0.5)
            
            wakeword_logger.info("Audio device released successfully")
            return True
        except Exception as e:
            wakeword_logger.error(f"Error releasing audio device: {e}")
            return False

    async def initialize_recorder(self):
        """Initialize recorder with retries and device cleanup."""
        if self.pv_recorder is None:
            for attempt in range(self._init_retries):
                try:
                    self.pv_recorder = PvRecorder(frame_length=self.porcupine.frame_length)
                    wakeword_logger.info("Recorder initialized successfully")
                    return True
                except Exception as e:
                    wakeword_logger.error(f"Attempt {attempt + 1}/{self._init_retries} "
                                        f"to initialize recorder failed: {e}")
                    
                    # On first failure, try to release the audio device
                    if attempt == 0:
                        await self._release_audio_device()
                    
                    if attempt < self._init_retries - 1:
                        await asyncio.sleep(self._retry_delay)
                        
            wakeword_logger.error("All initialization attempts failed")
            return False
        return True

    async def listen_for_wake_word(self, schedule_manager, py_recorder):
        tasks = set()
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries and not is_exit_event_set():
            try:
                if not await self.initialize_recorder():
                    retry_count += 1
                    await asyncio.sleep(self._retry_delay)
                    continue
                
                self.pv_recorder.start()
                wakeword_logger.info("Started listening for wake word")

                frame_bytes = []
                calibration_interval = 5
                last_button_check_time = time.time()
                last_calibration_time = time.time()
                button_check_interval = 1.5

                if self.play_trigger is None:
                    trigger_task = asyncio.create_task(
                        self.audio_player.play_trigger_with_logo(TriggerAudio, SeamanLogo)
                    )
                    tasks.add(trigger_task)
                    await trigger_task
                    self.play_trigger = True

                while not is_exit_event_set():
                    run_pending()

                    try:
                        audio_frame = self.pv_recorder.read()
                        audio_frame_bytes = np.array(audio_frame, dtype=np.int16).tobytes()
                        frame_bytes.append(audio_frame_bytes)

                        current_time = time.time()

                        if current_time - last_calibration_time >= calibration_interval:
                            frame_bytes = await self.calibrate_audio(py_recorder, frame_bytes)
                            last_calibration_time = current_time

                        detections = self.porcupine.process(audio_frame)
                        if detections >= 0:
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

                    except Exception as e:
                        wakeword_logger.error(f"Error processing audio frame: {e}")
                        await self.cleanup_recorder()
                        break

                    await asyncio.sleep(0.01)

            except Exception as e:
                wakeword_logger.error(f"Error in wake word detection: {e}")
                retry_count += 1
                await self.cleanup_recorder()
                if retry_count < max_retries:
                    wakeword_logger.info(f"Retrying... Attempt {retry_count}/{max_retries}")
                    await asyncio.sleep(self._retry_delay)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

        return False, None

    async def cleanup_recorder(self):
        """Clean up recorder with proper error handling."""
        if self.pv_recorder:
            try:
                self.pv_recorder.stop()
                self.pv_recorder.delete()
            except Exception as e:
                wakeword_logger.error(f"Error cleaning up recorder: {e}")
            finally:
                self.pv_recorder = None
                
    async def check_buttons(self):
        try:
            active_buttons = await self.server.get_buttons()
            if active_buttons[4]:  # RIGHT button
                wakeword_logger.info("Right Button Pressed")
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
# from display.setting import SettingMenu
# from pico.pico import PicoVoiceTrigger
# from utils.define import *
# from utils.scheduler import run_pending
# from utils.utils import is_exit_event_set

# from pvrecorder import PvRecorder

# import logging
# import numpy as np
# import time

# logging.basicConfig(level=logging.INFO)
# wakeword_logger = logging.getLogger(__name__)

# class WakeWord:
#     def __init__(self, args, audio_player):
#         self.audio_player = audio_player
#         self.pv_recorder = None 
#         self.play_trigger = None
#         self.porcupine = PicoVoiceTrigger(args)
#         self.server = args.server
#         self.setting_menu = None
#         # self.setting_menu = SettingMenu(audio_player=self.audio_player, serial_module=self.serial_module)
#         self.button_check_task = None
#         self.calibration_task = None
        
#     def initialize_recorder(self):
#         if self.pv_recorder is None:
#             try:
#                 self.pv_recorder = PvRecorder(frame_length=self.porcupine.frame_length)
#             except Exception as e:
#                 wakeword_logger.error(f"Failed to initialize recorder: {e}")
#                 raise

#     async def check_buttons(self):
#         try:
#             active_buttons = await self.server.get_buttons()
#             if active_buttons[4]: # RIGHT button
#                 wakeword_logger.info("Right Button Pressed")
#                 # response = self.setting_menu.display_menu()
#                 # if response:
#                 #     return response
#                 await asyncio.sleep(0.2)
#             return None
#         except Exception as e:
#             wakeword_logger.error(f"Error in check_buttons: {e}")
#             return None
        
#     async def calibrate_audio(self, py_recorder, frame_bytes):
#         try:
#             py_recorder.calibrate_energy_threshold(frame_bytes)
#             return []  
#         except Exception as e:
#             wakeword_logger.error(f"Error in calibration: {e}")
#             return frame_bytes
        
#     async def listen_for_wake_word(self, schedule_manager, py_recorder):
#         tasks = set()
#         try:
#             self.initialize_recorder()
#             self.pv_recorder.start()

#             frame_bytes = []
#             calibration_interval = 5
#             last_button_check_time = time.time()
#             last_calibration_time = time.time()
#             button_check_interval = 1.5 # 1.5 -> check buttons every 1.5 seconds
#             detections = -1

#             if self.play_trigger is None:
#                 trigger_task = asyncio.create_task(
#                     self.audio_player.play_trigger_with_logo(TriggerAudio, SeamanLogo)
#                 )
#                 tasks.add(trigger_task)
#                 await trigger_task
#                 self.play_trigger = True

#             while not is_exit_event_set():
#                 run_pending()

#                 # if schedule_manager.check_scheduled_conversation():
#                 #     return True, WakeWordType.SCHEDULE

#                 audio_frame = self.pv_recorder.read()
#                 audio_frame_bytes = np.array(audio_frame, dtype=np.int16).tobytes()
#                 frame_bytes.append(audio_frame_bytes)

#                 current_time = time.time() # timestamp

#                 if current_time - last_calibration_time >= calibration_interval:
#                         frame_bytes = await self.calibrate_audio(py_recorder, frame_bytes)
#                         last_calibration_time = current_time

#                 detections = self.porcupine.process(audio_frame)
#                 wake_word_triggered = detections >= 0
                
#                 if wake_word_triggered:
#                     wakeword_logger.info("Wake word detected")
#                     response_task = asyncio.create_task(
#                         self.audio_player.play_audio(ResponseAudio)
#                     )
#                     tasks.add(response_task)
#                     await response_task
#                     return True, WakeWordType.TRIGGER
                
#                 if current_time - last_button_check_time >= button_check_interval:
#                         button_task = asyncio.create_task(self.check_buttons())
#                         tasks.add(button_task)
#                         res = await button_task
                        
#                         if res == 'exit':
#                             exit_task = asyncio.create_task(
#                                 self.audio_player.play_trigger_with_logo(TriggerAudio, SeamanLogo)
#                             )
#                             tasks.add(exit_task)
#                             await exit_task
                        
#                         last_button_check_time = current_time

#                 await asyncio.sleep(0.01)

#         except KeyboardInterrupt:
#             return False, WakeWordType.OTHER
#         except Exception as e:
#             wakeword_logger.error(f"Error in wake word detection: {e}")
#             raise
#         finally:
#             for task in tasks:
#                 if not task.done():
#                     task.cancel()
#                     try:
#                         await task
#                     except asyncio.CancelledError:
#                         pass
#             await self.cleanup_recorder()

#         return False, None
    
#     def cleanup_recorder(self):
#         if self.pv_recorder:
#             try:
#                 self.pv_recorder.stop()
#                 self.pv_recorder.delete()
#                 self.pv_recorder = None
#             except Exception as e:
#                 wakeword_logger.error(f"Error cleaning up recorder: {e}")