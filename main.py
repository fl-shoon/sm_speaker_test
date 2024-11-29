from core import SpeakerCore
# from fireclient.fireclient import FireClient
from aiclient.conversation import ConversationClient
from localserver.serverManager import ServerManager
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
        self._cleanup_lock = asyncio.Lock()
        self._is_shutdown = False
        self._server_session = None

    async def initialize(self):
        """Initialize all components"""
        if self._is_shutdown:
            return False
        
        try:
            # Initialize AI client
            self.ai_client = ConversationClient()
            
            # Initialize server manager 
            self.server_manager = ServerManager(SERVER_URL)
            await self.server_manager.initialize()
            
            # Parse arguments
            args = self.setup_arguments()
            
            # Initialize core components
            try:
                self.speaker = SpeakerCore(args)
                # self.fire_client = FireClient()
                # self.schedule_manager = ScheduleManager(
                #     server_manager=self.server_manager,
                #     fire_client=self.fire_client
                # )
                self.ai_client.setAudioPlayer(self.speaker.audio_player)
            except Exception as e:
                main_logger.error(f"Failed to initialize speaker core: {e}")
                await self.cleanup()
                return False
            
            return True
        except Exception as e:
            main_logger.error(f"Initialization failed: {e}")
            return False

    def setup_arguments(self):
        """Setup command line arguments"""
        parser = argparse.ArgumentParser(description="Speaker Application")

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
        async with self._cleanup_lock:
            if self._is_shutdown:
                return
                
            self._is_shutdown = True
            main_logger.info("Starting application cleanup...")
            
            try:
                if hasattr(self.server_manager, 'session') and self.server_manager.session:
                    try:
                        await asyncio.wait_for(
                            self.server_manager.session.close(),
                            timeout=2.0
                        )
                    except Exception as e:
                        main_logger.error(f"Error closing server session: {e}")

                if self.speaker:
                    try:
                        await asyncio.wait_for(self.speaker.cleanup(), timeout=5.0)
                    except asyncio.TimeoutError:
                        main_logger.error("Speaker cleanup timed out")
                    except Exception as e:
                        main_logger.error(f"Error cleaning up speaker: {e}")
                    finally:
                        self.speaker = None

                if self.server_manager:
                    try:
                        await asyncio.wait_for(self.server_manager.cleanup(), timeout=3.0)
                    except asyncio.TimeoutError:
                        main_logger.error("Server cleanup timed out")
                    except Exception as e:
                        main_logger.error(f"Error cleaning up server: {e}")
                    finally:
                        self.server_manager = None

            except Exception as e:
                main_logger.error(f"Error during cleanup: {e}")
            finally:
                self.speaker = None
                self.server_manager = None
                self.fire_client = None
                self.schedule_manager = None
                self.ai_client = None
                
                await asyncio.sleep(0.5)
                main_logger.info("Application cleanup completed")

    def __del__(self):
        if not self._is_shutdown and asyncio.get_event_loop().is_running():
            asyncio.create_task(self.cleanup())

    async def run(self):
        try:
            if self._is_shutdown:
                return
            
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
    def signal_handler(signum, frame):
        signame = signal.Signals(signum).name
        main_logger.info(f"Received {signame} signal")
        set_exit_event()
        
        # Schedule cleanup in the event loop
        if app and not app._is_shutdown and asyncio.get_event_loop().is_running():
            asyncio.create_task(app.cleanup())
    
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
        asyncio.run(main())
    except KeyboardInterrupt:
        main_logger.info("Application terminated by user")
    except Exception as e:
        main_logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)