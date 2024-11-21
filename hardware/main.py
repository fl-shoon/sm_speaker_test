from display import DisplayModule
from manageDisplay import ManageDisplay
from player import AudioPlayer
from serverManager import ServerManager

import asyncio

async def main():
    try:
        # Initialize server manager
        serverManager = ServerManager()
        await serverManager.initialize()
        
        # Initialize display components
        displayManager = ManageDisplay(server_manger=serverManager)
        display = DisplayModule(display_manager=displayManager)  
        
        # Initialize audio
        player = AudioPlayer(display)
        
        if not hasattr(player, 'audio_available') or not player.audio_available:
            print("Warning: Audio not available. Continuing with display only.")
        
        try:
            # Your main logic here
            await player.play_trigger_with_logo("trigger.wav", "logo.png")
            await player.sync_audio_and_gif("audio.wav", "speakingGif.gif")
            
        except KeyboardInterrupt:
            print("\nStopping playback...")
            player.stop_playback()
            
        except Exception as e:
            print(f"Error during playback: {e}")
            
    except Exception as e:
        print(f"Error in main: {e}")
        
    finally:
        # Cleanup
        try:
            await display.cleanup_display()
        except Exception as e:
            print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
    except Exception as e:
        print(f"Fatal error: {e}")