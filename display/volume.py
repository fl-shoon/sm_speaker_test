from PIL import Image, ImageDraw, ImageFont, ImageEnhance

import io
import logging
import time

logging.basicConfig(level=logging.INFO)
volume_logger = logging.getLogger(__name__)

class SettingVolume:
    def __init__(self, serial_module, mcu_module, audio_player):
        self.serial_module = serial_module
        self.input_serial = mcu_module
        self.background_color = (73, 80, 87)
        self.text_color = (255, 255, 255)
        self.highlight_color = (0, 119, 255)
        self.display_size = (240, 240)
        self.audio_player = audio_player
        self.current_volume = self.audio_player.current_volume
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
                volume_logger.warning(f"Could not load font: {font_path}")
        
        volume_logger.error("Could not load any fonts. Using default font.")
        return None
    
    def create_volume_image(self):
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
        text = "音量"
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
        filled_height = int(bar_height * self.current_volume)
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
        volume_percentage = int(self.current_volume * 100)
        percentage_font = ImageFont.truetype(self.font_path, 14)
        percentage_text = f"{volume_percentage}"
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
        image = self.create_volume_image()

        # Apply current brightness to the image
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(self.serial_module.current_brightness)
        
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()

        self.serial_module.send_image_data(img_byte_arr)

    def draw_icon(self, draw, position):
        x, y = position
        size = 24  

        # Volume icon 
        icon_width = size * 0.9  
        icon_height = size * 0.9  
        speaker_width = icon_width * 0.4
        speaker_height = icon_height * 0.6

        # Calculate positions
        speaker_x = x + (size - speaker_width) // 2
        speaker_y = y + (size - speaker_height) // 2

        # Draw the speaker part
        draw.polygon([
            (speaker_x, speaker_y + speaker_height * 0.3),
            (speaker_x + speaker_width * 0.6, speaker_y + speaker_height * 0.3),
            (speaker_x + speaker_width, speaker_y),
            (speaker_x + speaker_width, speaker_y + speaker_height),
            (speaker_x + speaker_width * 0.6, speaker_y + speaker_height * 0.7),
            (speaker_x, speaker_y + speaker_height * 0.7)
        ], fill=(255, 255, 255))

        # Draw the three arcs
        arc_center_x = x + size * 0.7
        arc_center_y = y + size // 2
        for i in range(3):
            arc_radius = size * (0.15 + i * 0.1)  
            arc_bbox = [
                arc_center_x - arc_radius,
                arc_center_y - arc_radius,
                arc_center_x + arc_radius,
                arc_center_y + arc_radius
            ]
            draw.arc(arc_bbox, start=300, end=60, fill=(255, 255, 255), width=2)

    def run(self):
        self.update_display()
        while True:
            input_data = self.serial_module.get_inputs()
            if input_data and 'result' in input_data:
                result = input_data['result']
                buttons = result['buttons']

                if buttons[3]:  # UP button
                    self.current_volume = min(1.0, self.current_volume + 0.05)
                    self.update_display()
                    time.sleep(0.2)
                elif buttons[2]:  # DOWN button
                    self.current_volume = max(0.0, self.current_volume - 0.05)
                    self.update_display()
                    time.sleep(0.2)
                elif buttons[1]:  # RIGHT button
                    return 'confirm', self.current_volume
                elif buttons[0]:  # LEFT button
                    self.current_volume = self.audio_player.current_volume
                    return 'back', self.audio_player.current_volume
                else:
                    time.sleep(0.1)