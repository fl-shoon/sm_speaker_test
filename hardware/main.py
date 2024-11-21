from display import DisplayModule
from manageDisplay import ManageDisplay
from player import AudioPlayer
from serverManager import ServerManager

import asyncio

async def main():
    serverManager = ServerManager()
    displayManager = ManageDisplay(server_manger=serverManager)
    display = DisplayModule(display_manager=displayManager)  
    player = AudioPlayer(display)
    display.set_player_for_display(player)
    
    try:
        # Play trigger with logo
        await player.play_trigger_with_logo("trigger.wav", "logo.png")
        
        # Play audio with GIF
        await player.sync_audio_and_gif("audio.wav", "speakingGif.gif")
        
    except KeyboardInterrupt:
        player.stop_playback()
    finally:
        await display.cleanup_display()

if __name__ == "__main__":
    asyncio.run(main())