from display import DisplayModule
from manageDisplay import ManageDisplay
from player import AudioPlayer
from serverManager import ServerManager

import asyncio
import signal

async def cleanup(server_manager, display, player):
    """Cleanup function to properly close resources"""
    try:
        cleanup_tasks = []
        
        if player:
            player.stop_playback()
            
        if display:
            cleanup_tasks.append(display.cleanup_display())
            
        if server_manager:
            cleanup_tasks.append(server_manager.cleanup())
            
        if cleanup_tasks:
            # Wait for all cleanup tasks to complete
            await asyncio.gather(*cleanup_tasks)
        
        # Clean up any remaining tasks
        current_task = asyncio.current_task()
        for task in asyncio.all_tasks():
            if task is not current_task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
        await asyncio.sleep(0.1)
    except Exception as e:
        print(f"Error during cleanup: {e}")

async def main():
    server_manager = None
    display_manager = None
    display = None
    player = None
    
    try:
        # Initialize server
        server_manager = ServerManager("http://192.168.2.1:8080")
        await server_manager.initialize()
        
        # Initialize display
        display_manager = ManageDisplay(server_manger=server_manager)
        display = DisplayModule(display_manager=display_manager)  
        
        # Initialize audio
        player = AudioPlayer(display)
        
        # Create shutdown event
        shutdown_event = asyncio.Event()
        
        # Setup signal handler
        def signal_handler():
            print("\nReceived shutdown signal...")
            shutdown_event.set()
            
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        
        # Create and start trigger task
        trigger_task = asyncio.create_task(
            player.play_trigger_with_logo("trigger.wav", "logo.png")
        )
        shutdown_wait = asyncio.create_task(shutdown_event.wait())
        
        # Wait for either completion
        done, pending = await asyncio.wait(
            {trigger_task, shutdown_wait},
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # If trigger completed and no shutdown requested, start sync task
        if not shutdown_event.is_set() and trigger_task in done:
            sync_task = asyncio.create_task(
                player.sync_audio_and_gif("audio.wav", "speakingGif.gif")
            )
            shutdown_wait = asyncio.create_task(shutdown_event.wait())
            
            # Wait for either completion
            done, pending = await asyncio.wait(
                {sync_task, shutdown_wait},
                return_when=asyncio.FIRST_COMPLETED
            )
        
        # Cancel any pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            
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