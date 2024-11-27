from audio.player import AudioPlayer
from audio.recorder import PyRecorder
from utils.define import *
from display.display import DisplayModule
from display.manageDisplay import ManageDisplay
from utils.utils import is_exit_event_set
from wakeword.wakeword import WakeWord

import asyncio
import logging
import signal

logging.basicConfig(level=logging.INFO)
core_logger = logging.getLogger(__name__)

async def cleanup_resources(*resources):
    """Helper function to clean up multiple resources"""
    for resource in resources:
        if resource:
            try:
                if hasattr(resource, 'cleanup'):
                    await resource.cleanup()
                elif hasattr(resource, 'stop_stream'):
                    resource.stop_stream()
            except Exception as e:
                core_logger.error(f"Error cleaning up resource {resource}: {e}")

async def setup_signal_handlers(cleanup_callback):
    """Setup signal handlers for graceful shutdown"""
    loop = asyncio.get_running_loop()
    
    def handle_signal():
        core_logger.info("Received shutdown signal...")
        set_exit_event()
        asyncio.create_task(cleanup_callback())
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)
    
class SpeakerCore:
    def __init__(self, args):
        self.args = args
        self.ai_client = args.aiclient
        self.py_recorder = PyRecorder()
        self.tasks = set()
        
        # Initialize components
        self.display_manager = ManageDisplay(server_manger=args.server)
        self.display = DisplayModule(display_manager=self.display_manager)
        self.ai_client.set_display(display=self.display)
        self.audio_player = AudioPlayer(self.display)
        self.wake_word = WakeWord(args=args, audio_player=self.audio_player)
        
        core_logger.info("Speaker Core initialized successfully")

    async def run(self, schedule_manager):
        cleanup_attempted = False
        try:
            await setup_signal_handlers(self.cleanup)
            
            while not is_exit_event_set():
                try:
                    if not hasattr(self, 'device_retry_count'):
                        self.device_retry_count = 0
                    
                    # Create wake word listening task
                    wake_word_task = asyncio.create_task(
                        self.wake_word.listen_for_wake_word(
                            schedule_manager=schedule_manager,
                            py_recorder=self.py_recorder
                        )
                    )
                    self.tasks.add(wake_word_task)
                    
                    try:
                        res, trigger_type = await wake_word_task
                    except Exception as e:
                        core_logger.error(f"Wake word task failed: {e}")
                        # Force cleanup on critical errors
                        if not cleanup_attempted:
                            cleanup_attempted = True
                            await self.cleanup()
                        raise
                    finally:
                        self.tasks.remove(wake_word_task)
                    
                    # Reset retry count on successful operation
                    self.device_retry_count = 0
                    
                    if res:
                        if trigger_type == WakeWordType.TRIGGER:
                            await self.process_conversation()
                        elif trigger_type == WakeWordType.SCHEDULE:
                            await self.scheduled_conversation()
                    elif trigger_type == WakeWordType.OTHER:
                        await self.cleanup()
                        break
                    
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    self.device_retry_count += 1
                    core_logger.error(f"Error occurred in wake word listening: {e}")
                    
                    if not cleanup_attempted:
                        cleanup_attempted = True
                        await self.cleanup()
                        
                    if self.device_retry_count > 3:
                        core_logger.info("Too many device errors, reinitializing...")
                        break 

                    await asyncio.sleep(1)
                        
        except KeyboardInterrupt:
            core_logger.info("KeyboardInterrupt received, initiating shutdown...")
        except Exception as e:
            core_logger.error(f"Critical error in core run loop: {e}")
        finally:
            if not cleanup_attempted:
                await self.cleanup()

    async def cleanup(self):
        """Enhanced cleanup process"""
        core_logger.info("Starting cleanup process...")
        try:
            # Cancel all running tasks first
            for task in self.tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            cleanup_tasks = []
            
            # Clean up display first to ensure visual feedback
            if self.display:
                cleanup_tasks.append(self.display.send_white_frames())
                cleanup_tasks.append(self.display.cleanup_display())
            
            # Clean up wake word and recorder
            if self.wake_word:
                cleanup_tasks.append(self.wake_word.cleanup_recorder())
            
            if self.audio_player:
                await self.audio_player.cleanup()
                
            if cleanup_tasks:
                # Wait for cleanup tasks with timeout
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*cleanup_tasks, return_exceptions=True),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    core_logger.error("Cleanup tasks timed out")
                    
        except Exception as e:
            core_logger.error(f"Error during cleanup: {e}")
        finally:
            if self.display:
                try:
                    await self.display.send_white_frames()
                except Exception as e:
                    core_logger.error(f"Final display cleanup attempt failed: {e}")
            core_logger.info("Cleanup process completed")

    async def process_conversation(self):
        conversation_active = True
        silence_count = 0
        max_silence = 2
        display_task = None
        
        try:
            while conversation_active and not is_exit_event_set():
                # Start listening display in a separate task
                display_task = asyncio.create_task(
                    self.display.start_listening_display(SatoruHappy)
                )
                
                frames = await self.py_recorder.record_question(audio_player=self.audio_player)

                if not frames:
                    silence_count += 1
                    if silence_count >= max_silence:
                        core_logger.info("Maximum silence reached. Ending conversation.")
                        conversation_active = False
                    continue
                else:
                    silence_count = 0

                input_audio_file = AIOutputAudio
                self.py_recorder.save_audio(frames, input_audio_file)

                # Cancel display task and stop listening display
                if display_task and not display_task.done():
                    display_task.cancel()
                    try:
                        await display_task
                    except asyncio.CancelledError:
                        pass
                await self.display.stop_listening_display()

                try:
                    # Create tasks for concurrent operations
                    conversation_ended = await self.ai_client.process_audio(input_audio_file)
                    if conversation_ended:
                        conversation_active = False
                except Exception as e:
                    core_logger.error(f"Error processing conversation: {e}")
                    error_task = asyncio.create_task(
                        self.audio_player.sync_audio_and_gif(ErrorAudio, SpeakingGif)
                    )
                    await error_task
                    conversation_active = False

                await asyncio.sleep(0.1)

        finally:
            # Cleanup any running display task
            if display_task and not display_task.done():
                display_task.cancel()
                try:
                    await display_task
                except asyncio.CancelledError:
                    pass
            # Show final logo
            await self.display.fade_in_logo(SeamanLogo)

    async def scheduled_conversation(self):
        conversation_active = True
        silence_count = 0
        max_silence = 2
        text_initiation = "こんにちは"
        display_task = None

        try:
            core_logger.info("Starting scheduled conversation")
            conversation_ended, _ = await self.ai_client.process_text(text_initiation)
            
            if conversation_ended:
                core_logger.info("Conversation ended after initial greeting")
                await self.display.fade_in_logo(SeamanLogo)
                return

            await asyncio.sleep(0.5)

            while conversation_active and not is_exit_event_set():
                display_task = asyncio.create_task(
                    self.display.start_listening_display(SatoruHappy)
                )
                
                frames = await self.py_recorder.record_question(audio_player=self.audio_player)

                if not frames:
                    silence_count += 1
                    if silence_count >= max_silence:
                        core_logger.info("Maximum silence reached. Ending conversation.")
                        conversation_active = False
                    continue
                else:
                    silence_count = 0

                input_audio_file = AIOutputAudio
                self.py_recorder.save_audio(frames, input_audio_file)

                # Cancel display task and stop listening display
                if display_task and not display_task.done():
                    display_task.cancel()
                    try:
                        await display_task
                    except asyncio.CancelledError:
                        pass
                await self.display.stop_listening_display()

                try:
                    conversation_ended = await self.ai_client.process_audio(input_audio_file)
                    if conversation_ended:
                        conversation_active = False
                except Exception as e:
                    core_logger.error(f"Error processing conversation: {e}")
                    error_task = asyncio.create_task(
                        self.audio_player.sync_audio_and_gif(ErrorAudio, SpeakingGif)
                    )
                    await error_task
                    conversation_active = False

                await asyncio.sleep(0.1)

        except Exception as e:
            core_logger.error(f"Error in scheduled conversation: {e}")
            error_task = asyncio.create_task(
                self.audio_player.sync_audio_and_gif(ErrorAudio, SpeakingGif)
            )
            await error_task
        finally:
            # Cleanup any running display task
            if display_task and not display_task.done():
                display_task.cancel()
                try:
                    await display_task
                except asyncio.CancelledError:
                    pass
            await self.display.fade_in_logo(SeamanLogo)

    async def cleanup(self):
        core_logger.info("Starting cleanup process...")
        try:
            cleanup_tasks = []
            
            if self.py_recorder:
                try:
                    self.py_recorder.stop_stream()
                except Exception as e:
                    core_logger.error(f"Error stopping recorder: {e}")
                    
            if self.display:
                try:
                    cleanup_tasks.append(self.display.send_white_frames())
                    cleanup_tasks.append(self.display.cleanup_display())
                except Exception as e:
                    core_logger.error(f"Error in display cleanup: {e}")
                    
            if self.audio_player:
                await self.audio_player.cleanup()
                self.audio_player = None
            
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks)
                    
        except Exception as e:
            core_logger.error(f"Error during cleanup: {e}")
        finally:
            core_logger.info("Cleanup process completed.")