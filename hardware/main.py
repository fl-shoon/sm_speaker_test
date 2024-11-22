from display import DisplayModule
from manageDisplay import ManageDisplay
from player import AudioPlayer
from serverManager import ServerManager

import asyncio

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
        
        await player.play_trigger_with_logo("trigger.wav", "logo.png")
        await player.sync_audio_and_gif("audio.wav", "speakingGif.gif")
            
    except KeyboardInterrupt:
        if player:
            player.stop_playback()
    except Exception as e:
        print(f"Error in main: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if display:
            await display.cleanup_display()
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(main())