from contextlib import contextmanager
from PIL import Image, ImageEnhance

import asyncio
import io 
import logging
import os

logging.basicConfig(level=logging.INFO)
display_logger = logging.getLogger(__name__)

@contextmanager
def suppress_stdout_stderr():
    """A context manager that redirects stdout and stderr to devnull"""
    try:
        null = os.open(os.devnull, os.O_RDWR)
        save_stdout, save_stderr = os.dup(1), os.dup(2)
        os.dup2(null, 1)
        os.dup2(null, 2)
        yield
    finally:
        os.dup2(save_stdout, 1)
        os.dup2(save_stderr, 2)
        os.close(null)

class DisplayModule:
    def __init__(self, display_manager):
        self.display_manager = display_manager
        self.fade_in_steps = 7
        self.player = None

    def set_player_for_display(self, player):
        self.player = player
        
    async def fade_in_logo(self, logo_path):
        """Fade in a logo image with brightness control"""
        try: 
            img = Image.open(logo_path)
            width, height = img.size
            
            for i in range(self.fade_in_steps):
                alpha = int(255 * (i + 1) / self.fade_in_steps)
                current_brightness = self.display_manager.current_brightness * (i + 1) / self.fade_in_steps

                faded_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                faded_img.paste(img, (0, 0))
                faded_img.putalpha(alpha)

                rgb_img = Image.new("RGB", faded_img.size, (0, 0, 0))
                rgb_img.paste(faded_img, mask=faded_img.split()[3])

                enhancer = ImageEnhance.Brightness(rgb_img)
                brightened_img = enhancer.enhance(current_brightness)

                encoded_data = self.display_manager.encode_image_to_bytes(brightened_img)
                await self.display_manager.send_image(encoded_data)
                await asyncio.sleep(0.01)
        except Exception as e:
            display_logger.error(f"Error in fade_in_logo: {e}")
            raise

    async def update_gif(self, gif_path): 
        try:
            frames = self.display_manager.prepare_gif(gif_path)
            if not frames:
                display_logger.error("No frames loaded from GIF")
                return
                
            encoded_frames = self.display_manager.precompute_frames(frames)
            frame_count = len(encoded_frames)
            
            if frame_count == 0:
                display_logger.error("No frames encoded from GIF")
                return
                
            frame_index = 0
            display_logger.info(f"Starting GIF playback with {frame_count} frames")
            
            while self.player.playback_active:
                try:
                    encoded_data = encoded_frames[frame_index]
                    await self.display_manager.send_image(encoded_data)
                    
                    frame_index = (frame_index + 1) % frame_count
                    await asyncio.sleep(0.1)  
                    
                except Exception as e:
                    display_logger.error(f"Error displaying frame {frame_index}: {e}")
                    raise
                    
        except Exception as e:
            display_logger.error(f"Error in update_gif: {e}")
            raise

    async def display_image(self, image_path):
        try:
            img = Image.open(image_path)

            if img.mode != 'RGB':
                img = img.convert('RGB')

            if img.size != (240, 240):
                img = img.resize((240, 240))

            brightened_img = self.display_manager.apply_brightness(img)

            encoded_data = self.display_manager.encode_image_to_bytes(brightened_img)
            await self.display_manager.send_image(encoded_data)

        except Exception as e:
            display_logger.warning(f"Error in display_image: {e}")

    async def start_listening_display(self, image_path):
        await self.display_image(image_path)

    async def send_white_frames(self):
        await self.display_manager.send_white_frames()

    async def stop_listening_display(self):
        await self.send_white_frames()

    async def cleanup_display(self):
        await self.display_manager.cleanup_server()