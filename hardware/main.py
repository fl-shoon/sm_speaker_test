from display import DisplayModule
from manageDisplay import ManageDisplay
from player import AudioPlayer
from serverManager import ServerManager
from jsonrpc_async import Server  

import asyncio
import sys

async def main():
    server_manager = None
    display_manager = None
    display = None
    player = None
    
    try:
        # Initialize ServerManager with proper server
        server_manager = ServerManager("http://192.168.2.1:8080")
        await server_manager.initialize()
        
        # Initialize other components
        display_manager = ManageDisplay(server_manger=server_manager)
        display = DisplayModule(display_manager=display_manager)  
        
        # Initialize audio
        player = AudioPlayer(display)
        display.set_player_for_display(player)
        
        # Your main logic here
        await player.play_trigger_with_logo("trigger.wav", "logo.png")
        await player.sync_audio_and_gif("audio.wav", "speakingGif.gif")
            
    except KeyboardInterrupt:
        print("\nStopping playback...")
        if player:
            player.stop_playback()
    except Exception as e:
        print(f"Error in main: {e}")
        raise  # Add this to see full traceback
    finally:
        if display:
            try:
                await display.cleanup_display()
            except Exception as e:
                print(f"Error during display cleanup: {e}")

if __name__ == "__main__":
    asyncio.run(main())