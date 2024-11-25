from display import DisplayModule
from manageDisplay import ManageDisplay
from player import AudioPlayer
from serverManager import ServerManager

import asyncio
import signal

async def cleanup(server_manager, display, player):
    """Cleanup function to properly close resources"""
    if player:
        player.stop_playback()
    if display:
        await display.cleanup_display()
    if server_manager and hasattr(server_manager.server, '_session'):
        await server_manager.cleanup()
    await asyncio.sleep(0.1)

async def main():
    server_manager = None
    display_manager = None
    display = None
    player = None
    
    # Create an event to signal shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        shutdown_event.set()
    
    try:
        # Initialize server
        server_manager = ServerManager("http://192.168.2.1:8080")
        await server_manager.initialize()
        
        # Initialize display
        display_manager = ManageDisplay(server_manger=server_manager)
        display = DisplayModule(display_manager=display_manager)  
        
        # Initialize audio
        player = AudioPlayer(display)
        
        # Add signal handler
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        
        # Create tasks
        trigger_task = asyncio.create_task(
            player.play_trigger_with_logo("trigger.wav", "logo.png")
        )
        
        # Wait for either task completion or shutdown signal
        await asyncio.wait(
            [trigger_task, shutdown_event.wait()],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        if not shutdown_event.is_set():
            sync_task = asyncio.create_task(
                player.sync_audio_and_gif("audio.wav", "speakingGif.gif")
            )
            await asyncio.wait(
                [sync_task, shutdown_event.wait()],
                return_when=asyncio.FIRST_COMPLETED
            )
            
    except Exception as e:
        print(f"Error in main: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        await cleanup(server_manager, display, player)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested...")