from PIL import Image, ImageEnhance

import io
import numpy as np

class ManageDisplay:
    def __init__(self, server_manger):
        self.current_brightness = 1.0  
        self.current_image = None
        self.server = server_manger

    def apply_brightness(self, img):
        enhancer = ImageEnhance.Brightness(img)
        return enhancer.enhance(self.current_brightness)
    
    def set_brightness(self, brightness):
        self.current_brightness = max(0.0, min(1.0, brightness))

    def frame_to_bytes(self, frame):
        """Convert numpy array frame to hex string"""
        img = Image.fromarray(frame)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        # Convert to hex string for JSON serialization
        return img_byte_arr.getvalue().hex()

    def prepare_gif(self, gif_path, target_size=(240, 240)):
        """Prepare GIF frames for display"""
        frames = []
        try:
            gif = Image.open(gif_path)
            # Add first frame
            frame = gif.copy().convert('RGB').resize(target_size)
            frames.append(np.array(frame))
            
            # Process remaining frames
            while True:
                try:
                    gif.seek(gif.tell() + 1)
                    frame = gif.copy().convert('RGB').resize(target_size)
                    frames.append(np.array(frame))
                except EOFError:
                    break
        except Exception as e:
            print(f"Error preparing GIF: {e}")
            return []
        return frames
    
    def encode_image_to_bytes(self, image):
        """Convert PIL Image to bytes that can be JSON serialized"""
        if isinstance(image, Image.Image):
            img_byte_arr = io.BytesIO()
            if image.mode != 'RGB':
                image = image.convert('RGB')
            image.save(img_byte_arr, format='PNG')
            # Convert bytes to hex string for JSON serialization
            return img_byte_arr.getvalue().hex()
        elif isinstance(image, str):
            return image  # If already hex string, return as is
        else:
            raise ValueError(f"Unsupported image type: {type(image)}")
    
    def precompute_frames(self, frames):
        return [self.frame_to_bytes(frame) for frame in frames]
    
    def create_solid_screen(self, color=(255, 255, 255), size=(240, 240)):
        """Create a solid color screen
        Args:
            color (tuple, optional): RGB color. Defaults to white (255, 255, 255)
            size (tuple, optional): Image size. Defaults to (240, 240)
        Returns:
            PIL.Image: Solid color image
        """
        return Image.new("RGBA", size, color)
    
    async def send_white_frames(self):
        try:
            white_screen = self.create_solid_screen()
            encoded_data = self.encode_image_to_bytes(white_screen)  # Add this line
            await self.server.show_image(encoded_data)  # Modify this line
        except Exception as e:
            print(f"Error sending white frames: {e}")

    async def send_image(self, encoded_img):
        await self.server.show_image(encoded_img)

    async def cleanup_server(self):
        await self.server.cleanup()