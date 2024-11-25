from PIL import Image, ImageDraw, ImageFont, ImageEnhance

import io 
import logging
import math
import time 

logging.basicConfig(level=logging.INFO)
brightness_logger = logging.getLogger(__name__)

class SettingBrightness:
    def __init__(self, serial_module, mcu_module):
        self.serial_module = serial_module
        self.input_serial = mcu_module
        self.background_color = (73, 80, 87)
        self.text_color = (255, 255, 255)
        self.highlight_color = (0, 119, 255)
        self.display_size = (240, 240)
        self.current_brightness = self.serial_module.current_brightness
        self.font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
        self.font = self.load_font()

    def load_font(self):
        font_paths = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",  
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  
        ]
        
        for font_path in font_paths:
            try:
                return ImageFont.truetype(font_path, 20)
            except IOError:
                brightness_logger.warning(f"Could not load font: {font_path}")
        
        brightness_logger.error("Could not load any fonts. Using default font.")
        return None
    
    def create_brightness_image(self):
        if self.font is None:
            return None
        
        image = Image.new('RGB', self.display_size, self.background_color)
        draw = ImageDraw.Draw(image)

        # Draw brightness icon and text
        icon_size = 24
        icon_x = self.display_size[0] // 2 - icon_size // 2
        icon_y = 20
        self.draw_icon(draw, (icon_x, icon_y))
        
        small_font = ImageFont.truetype(self.font_path, 14)
        text = "輝度"
        text_bbox = draw.textbbox((0, 0), text, font=small_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = self.display_size[0] // 2 - text_width // 2
        draw.text((text_x, icon_y + icon_size + 5), text, font=small_font, fill=self.text_color)

        # Draw vertical brightness bar
        bar_width = 20
        bar_height = 140
        bar_x = (self.display_size[0] - bar_width) // 2
        bar_y = 80
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], outline=self.text_color)
        filled_height = int(bar_height * self.current_brightness)
        draw.rectangle([bar_x, bar_y + bar_height - filled_height, bar_x + bar_width, bar_y + bar_height], fill=self.highlight_color)

        # Draw white horizontal bar (slider)
        slider_width = 30
        slider_height = 4
        slider_y = bar_y + bar_height - filled_height - slider_height // 2
        draw.rectangle([bar_x - (slider_width - bar_width) // 2, slider_y, 
                        bar_x + bar_width + (slider_width - bar_width) // 2, slider_y + slider_height], 
                    fill=self.text_color)

        # Draw brightness value in a circle
        value_size = 30
        value_x = bar_x + bar_width + 20
        value_y = slider_y + slider_height // 2
        draw.ellipse([value_x, value_y - value_size//2, value_x + value_size, value_y + value_size//2], fill=self.text_color)
        brightness_percentage = int(self.current_brightness * 100)
        percentage_font = ImageFont.truetype(self.font_path, 14)
        percentage_text = f"{brightness_percentage}"
        text_bbox = draw.textbbox((0, 0), percentage_text, font=percentage_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = value_x + (value_size - text_width) // 2
        text_y = value_y - text_height // 2
        vertical_adjustment = -1  
        text_y += vertical_adjustment
        draw.text((text_x, text_y), percentage_text, font=percentage_font, fill=self.background_color)

        # Draw navigation buttons
        draw.polygon([(20, 120), (30, 110), (30, 130)], fill=self.text_color)  # Left arrow
        draw.polygon([(220, 120), (210, 110), (210, 130)], fill=self.text_color)  # Right arrow
        fixFont = ImageFont.truetype(self.font_path, 12)
        draw.text((20, 135), "戻る", font=fixFont, fill=self.text_color)
        draw.text((200, 135), "決定", font=fixFont, fill=self.text_color)

        return image

    def update_display(self):
        image = self.create_brightness_image()
        
        # Apply current brightness to the image
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(self.current_brightness)

        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()

        self.serial_module.send_image_data(img_byte_arr)

    def draw_icon(self, draw, position):
        x, y = position
        size = 24  

        # Half-filled sun icon
        center = size // 2
        
        # Draw the full circle outline
        draw.ellipse([x+size*0.17, y+size*0.17, x+size*0.83, y+size*0.83], outline=self.text_color, width=2)
        
        # Fill the left half of the circle
        draw.pieslice([x+size*0.17, y+size*0.17, x+size*0.83, y+size*0.83], start=90, end=270, fill=self.text_color)
        
        # Draw the rays
        for i in range(8):
            angle = i * 45
            x1 = x + center + int(size*0.58 * math.cos(math.radians(angle)))
            y1 = y + center + int(size*0.58 * math.sin(math.radians(angle)))
            x2 = x + center + int(size*0.42 * math.cos(math.radians(angle)))
            y2 = y + center + int(size*0.42 * math.sin(math.radians(angle)))
            draw.line([x1, y1, x2, y2], fill=self.text_color, width=2)

    def run(self):
        self.update_display()
        while True:
            input_data = self.serial_module.get_inputs()
            if input_data and 'result' in input_data:
                result = input_data['result']
                buttons = result['buttons']

                if buttons[3]:  # UP button
                    self.current_brightness = min(1.0, self.current_brightness + 0.05)
                    self.update_display()
                    time.sleep(0.2)
                elif buttons[2]:  # DOWN button
                    self.current_brightness = max(0.0, self.current_brightness - 0.05)
                    self.update_display()
                    time.sleep(0.2)
                elif buttons[1]:  # RIGHT button
                    return 'confirm', self.current_brightness
                elif buttons[0]:  # LEFT button
                    self.current_brightness = self.serial_module.current_brightness
                    return 'back', self.serial_module.current_brightness
                else:
                    time.sleep(0.1)
