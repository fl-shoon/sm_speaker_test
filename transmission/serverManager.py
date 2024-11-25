from jsonrpc_async import Server
from PIL import Image, ImageFont, ImageDraw

import aiohttp
import asyncio
import subprocess

class ServerManager:
    def __init__(self, address=None):
        if address is None:
            self.address = "http://localhost:8080"
        else:
            self.address = address
        
        try:
            self.font = ImageFont.truetype("/Users/nobo/Library/Fonts/NotoSansCJKjp-Regular.otf", 24)
        except:
            print("Warning: Default font not found. Some text rendering features may not work.")
            self.font = None

        self.server = None
        self.btn_data = [False, False, False, False, False]
        self.max_retries = 3
        self.retry_delay = 2
        self._session = None
        
    async def initialize(self):
        for attempt in range(self.max_retries):
            try:
                if self._session is None:
                    self._session = aiohttp.ClientSession()
                
                self.server = Server(self.address, session=self._session)
                await self.server.Buttons()
                print(f"Successfully connected to server at {self.address}")
                return self.server
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"Connection attempt {attempt + 1} failed: {e}")
                    print(f"Retrying in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    print(f"Failed to initialize server after {self.max_retries} attempts: {e}")
                    print(f"Please verify the server is running at: {self.address}")
                    await self._cleanup_session()
                    raise
        
    async def _cleanup_session(self):
        """Clean up the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            await asyncio.sleep(0.1)
        self._session = None

    async def cleanup(self):
        """Clean up server resources"""
        try:
            await self._cleanup_session()
        except Exception as e:
            print(f"Error during server cleanup: {e}")

    async def reconnect(self):
        """Attempt to reconnect to the server"""
        try:
            await self.cleanup()
            await self.initialize()
        except Exception as e:
            print(f"Reconnection failed: {e}")
            raise

    async def show_image(self, encoded_img):
        """Display an image on the LCD screen with retry on failure"""
        for attempt in range(self.max_retries):
            try:
                if self.server:
                    await self.server.LcdShow(image=encoded_img)
                    return
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"Show image failed, attempting to reconnect...")
                    await self.reconnect()
                else:
                    print(f"Error showing image after {self.max_retries} attempts: {e}")
                    raise

    async def get_buttons(self):
        """Get button states and detect new presses"""
        try:
            buttons = await self.server.Buttons()
            active = [not self.btn_data[i] and v for i, v in enumerate(buttons)]
            self.btn_data = buttons
            return active
        except Exception as e:
            print(f"Error getting button states: {e}")
            return [False] * 5
    
    async def get_sensors(self):
        """
        各種センサの値を取得、返値例:
        {
            'motion': False,       # 人検知センサ(True:動き有り)
            'temperature': 25.541, # 温度[celsius]
            'humidity': 46.406,    # 相対湿度[%]
            'lux1': 91,            # UVの明るさ[lux]
            'lux2': 169            # 可視光＋UVの明るさ[lux]
        }
        """
        try:
            sensors = await self.server.Sensors()
            return sensors if sensors else {}
        except Exception as e:
            print(f"Error getting sensor data: {e}")
            return {}
        
    async def set_lcd_config(self, backlight=None):
        """Configure LCD settings
        Args:
            backlight (int, optional): Backlight brightness 0-100
        """
        try:
            config = {}
            if backlight is not None:
                config['backlight'] = max(0, min(100, backlight))
            if config:
                await self.server.LcdConfig(**config)
        except Exception as e:
            print(f"Error configuring LCD: {e}")

    async def set_motor(self, deg):
        """Set motor position
        Args:
            deg (int): Target position in degrees
        """
        try:
            await self.server.MotorSet(deg=deg)
        except Exception as e:
            print(f"Error setting motor position: {e}")

    async def reset_motor(self, deg=-90):
        """Reset motor to home position
        Args:
            deg (int, optional): Home position in degrees. Defaults to -90
        """
        try:
            await self.server.MotorReset(deg=deg)
        except Exception as e:
            print(f"Error resetting motor: {e}")

    # Utility methods for image handling
    def create_text_image(self, text, size=(240, 240), offset=(0, 0), 
                         color=(0, 0, 0), background=(255, 255, 255)):
        """Create an image with text
        Args:
            text (str): Text to display
            size (tuple, optional): Image size. Defaults to (240, 240)
            offset (tuple, optional): Text offset from center. Defaults to (0, 0)
            color (tuple, optional): Text color RGB. Defaults to black
            background (tuple, optional): Background color RGB. Defaults to white
        """
        if not self.font:
            raise Exception("Font not initialized")

        img = Image.new("RGBA", size, background)
        draw = ImageDraw.Draw(img)
        draw.text(
            (size[0]/2 + offset[0], size[1]/2 + offset[1]),
            text,
            color,
            font=self.font,
            anchor="mm"
        )
        return img

    def build_composite_image(self, *image_paths, size=(240, 240)):
        """Build a composite image from multiple image files
        Args:
            *image_paths: Variable number of image file paths
            size (tuple, optional): Target size. Defaults to (240, 240)
        """
        if not image_paths:
            raise ValueError("At least one image path is required")

        try:
            base_img = Image.open(image_paths[0]).resize(size)
            for path in image_paths[1:]:
                overlay = Image.open(path).resize(size)
                base_img.alpha_composite(overlay)
            return base_img
        except Exception as e:
            print(f"Error building composite image: {e}")
            raise

    def power_off(self):
        active = self.get_buttons()
        if active[0]:
            subprocess.run("poweroff")