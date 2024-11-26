from display.setting import SettingMenu
from pico.pico import PicoVoiceTrigger
from utils.define import *
from utils.scheduler import run_pending
from utils.utils import is_exit_event_set
from .static_recorder import PvRecorder

import logging
import numpy as np
import time
import asyncio

logging.basicConfig(level=logging.INFO)
wakeword_logger = logging.getLogger(__name__)

class WakeWord:
    def __init__(self, args, audio_player):
        self.audio_player = audio_player
        self.pv_recorder = None
        self.play_trigger = None
        self.porcupine = PicoVoiceTrigger(args)
        self.server = args.server
        self.fallback_mode = False
        self._recorder_init_retries = 3
        self._recorder_init_delay = 2
        
    async def initialize_recorder(self):
        """Initialize recorder with retries and fallback mechanism"""
        if self.pv_recorder is None:
            for attempt in range(self._recorder_init_retries):
                try:
                    self.pv_recorder = PvRecorder(frame_length=self.porcupine.frame_length)
                    self.pv_recorder.start()
                    self.fallback_mode = False
                    return True
                except Exception as e:
                    wakeword_logger.warning(f"Attempt {attempt + 1}/{self._recorder_init_retries} "
                                          f"to initialize recorder failed: {e}")
                    if attempt < self._recorder_init_retries - 1:
                        await asyncio.sleep(self._recorder_init_delay)
            
            wakeword_logger.error("All recorder initialization attempts failed.")
            return False

    async def check_buttons(self):
        try:
            active_buttons = await self.server.get_buttons()
            if active_buttons[4]: # RIGHT button
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
        
    async def listen_for_wake_word(self, schedule_manager, py_recorder):
        tasks = set()
        try:
            # Initialize recorder
            recorder_initialized = await self.initialize_recorder()
            if not recorder_initialized:
                wakeword_logger.info("Using default recorder")
                # Use py_recorder directly instead of falling back
                self.pv_recorder = py_recorder
                
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
                    # Unified audio reading approach
                    if isinstance(self.pv_recorder, PvRecorder):
                        audio_frame = self.pv_recorder.read()
                    else:
                        # For py_recorder
                        audio_frame = await self.pv_recorder.record_frame()
                        
                    if audio_frame is None:
                        await asyncio.sleep(0.01)
                        continue
                        
                    audio_frame = np.array(audio_frame, dtype=np.int16)
                    audio_frame_bytes = audio_frame.tobytes()
                    frame_bytes.append(audio_frame_bytes)

                    current_time = time.time()

                    if current_time - last_calibration_time >= calibration_interval:
                        frame_bytes = await self.calibrate_audio(py_recorder, frame_bytes)
                        last_calibration_time = current_time

                    # Process audio with Porcupine
                    detections = self.porcupine.process(audio_frame)
                    if detections >= 0:
                        wakeword_logger.info("Wake word detected")
                        response_task = asyncio.create_task(
                            self.audio_player.play_audio(ResponseAudio)
                        )
                        tasks.add(response_task)
                        await response_task
                        return True, WakeWordType.TRIGGER

                except Exception as e:
                    wakeword_logger.error(f"Error processing audio frame: {e}")
                    await asyncio.sleep(0.01)
                    continue

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

        except Exception as e:
            wakeword_logger.error(f"Error in wake word detection: {e}")
            return False, WakeWordType.OTHER
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
        """Clean up recorder resources."""
        if isinstance(self.pv_recorder, PvRecorder):
            try:
                self.pv_recorder.stop()
                self.pv_recorder.delete()
            except Exception as e:
                wakeword_logger.error(f"Error cleaning up recorder: {e}")
        self.pv_recorder = None