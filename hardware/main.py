from display import DisplayModule
from manageDisplay import ManageDisplay
from player import AudioPlayer
from serverManager import ServerManager

import asyncio
import sys

async def main():
    server_manager = None
    display_manager = None
    display = None
    player = None
    
    try:
        # Initialize server manager
        server_manager = ServerManager()
        await server_manager.initialize()
        
        # Initialize display components
        display_manager = ManageDisplay(server_manger=server_manager)
        display = DisplayModule(display_manager=display_manager)  
        
        # Initialize audio
        player = AudioPlayer(display)
        display.set_player_for_display(player)
        
        await player.play_trigger_with_logo("trigger.wav", "logo.png")
        await player.sync_audio_and_gif("audio.wav", "speakingGif.gif")
        
    except KeyboardInterrupt:
        print("\nStopping playback...")
        if player:
            player.stop_playback()
    except Exception as e:
        print(f"Error in main: {e}", file=sys.stderr)
    finally:
        if display:
            try:
                await display.cleanup_display()
            except Exception as e:
                print(f"Error during display cleanup: {e}", file=sys.stderr)
        
        if server_manager:
            try:
                await server_manager.cleanup()
            except Exception as e:
                print(f"Error during server cleanup: {e}", file=sys.stderr)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)