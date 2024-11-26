from core import SpeakerCore
# from fireclient.fireclient import FireClient
from aiclient.conversation import ConversationClient
from transmission.serverManager import ServerManager
from utils.define import *
from utils.scheduler import ScheduleManager
from utils.utils import set_exit_event, is_exit_event_set

import asyncio
import argparse
import logging
import os
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
main_logger = logging.getLogger(__name__)

class Application:
    def __init__(self):
        self.speaker = None
        self.server_manager = None
        self.fire_client = None
        self.schedule_manager = None
        self.ai_client = None

    async def initialize(self):
        """Initialize all components"""
        try:
            # Initialize AI client
            self.ai_client = ConversationClient()
            
            # Initialize server manager with retry logic
            self.server_manager = ServerManager("http://192.168.2.1:8080")
            await self.server_manager.initialize()
            
            # Parse arguments
            args = self.setup_arguments()
            
            # Initialize core components
            self.speaker = SpeakerCore(args)
            # self.fire_client = FireClient()
            # self.schedule_manager = ScheduleManager(
            #     server_manager=self.server_manager,
            #     fire_client=self.fire_client
            # )
            self.ai_client.setAudioPlayer(self.speaker.audio_player)
            
            return True
        except Exception as e:
            main_logger.error(f"Initialization failed: {e}")
            return False

    def setup_arguments(self):
        """Setup command line arguments"""
        parser = argparse.ArgumentParser(description="Speaker Application")
        
        # Pico wake word arguments
        parser.add_argument(
            '--access_key',
            help='AccessKey for Porcupine',
            default=os.environ.get("PICO_ACCESS_KEY")
        )
        parser.add_argument(
            '--keyword_paths',
            nargs='+',
            help="Paths to keyword model files",
            default=[PicoWakeWordKonnichiwa, PicoWakeWordSatoru]
        )
        parser.add_argument(
            '--model_path',
            help='Path to Porcupine model file',
            default=PicoLangModel
        )
        parser.add_argument(
            '--sensitivities',
            nargs='+',
            help="Sensitivities for keywords",
            type=float,
            default=[0.9, 0.9]  # Updated to use higher sensitivity
        )
        parser.add_argument(
            '--gain',
            type=float,
            help='Audio gain multiplier',
            default=5.0
        )

        # Client arguments
        parser.add_argument(
            '--aiclient',
            help='Asynchronous openAi client',
            default=self.ai_client
        )
        parser.add_argument(
            '--server',
            help='Server manager instance',
            default=self.server_manager
        )

        return parser.parse_args()

    async def cleanup(self):
        """Cleanup all resources"""
        main_logger.info("Starting application cleanup...")
        cleanup_tasks = []
        
        try:
            # Clean up speaker core
            if self.speaker:
                cleanup_tasks.append(self.speaker.cleanup())
            
            # Clean up server manager
            if self.server_manager:
                cleanup_tasks.append(self.server_manager.cleanup())
            
            # Wait for all cleanup tasks to complete
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                
        except Exception as e:
            main_logger.error(f"Error during cleanup: {e}")
        finally:
            main_logger.info("Application cleanup completed")

    async def run(self):
        """Main application run loop"""
        try:
            # Initialize all components
            if not await self.initialize():
                main_logger.error("Initialization failed, exiting...")
                return
            
            # Run the speaker core
            # await self.speaker.run(self.schedule_manager)
            await self.speaker.run(None)
            
        except KeyboardInterrupt:
            main_logger.info("KeyboardInterrupt received, initiating shutdown...")
        except Exception as e:
            main_logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        finally:
            await self.cleanup()

def setup_signal_handlers(app):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        signame = signal.Signals(signum).name
        main_logger.info(f"Received {signame} signal")
        set_exit_event()
        
        # Schedule cleanup in the event loop
        if app and asyncio.get_event_loop().is_running():
            asyncio.create_task(app.cleanup())
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

async def main():
    """Main entry point"""
    app = Application()
    
    try:
        # Setup signal handlers
        setup_signal_handlers(app)
        
        # Run the application
        await app.run()
        
    except Exception as e:
        main_logger.error(f"Fatal error in main: {e}", exc_info=True)
        await app.cleanup()
        sys.exit(1)

if __name__ == '__main__':
    try:
        # Run the async main function
        asyncio.run(main())
    except KeyboardInterrupt:
        main_logger.info("Application terminated by user")
    except Exception as e:
        main_logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)