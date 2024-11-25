from display.brightness import SettingBrightness
from display.volume import SettingVolume
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

import io
import logging
import math
import time

logging.basicConfig(level=logging.INFO)
setting_logger = logging.getLogger(__name__)

class SettingMenu:
    def __init__(self, audio_player, serial_module):
        self.serial_module = serial_module
        self.input_serial = serial_module.input_serial
        
        self.background_color = (73, 80, 87)
        self.text_color = (255, 255, 255)
        self.highlight_color = (255, 255, 255)
        self.display_size = (240, 240)
        self.highlight_text_color = (0, 0, 0)
        self.icon_size = 24
        self.font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
        
        self.menu_items = [
            {'icon': 'volume', 'text': '音量'},
            {'icon': 'brightness', 'text': '輝度'},
            {'icon': 'character', 'text': 'キャラ'},
            {'icon': 'settings', 'text': '設定'},
            {'icon': 'exit', 'text': '終了'}
        ]
        
        self.selected_item = 1
        self.font = self.load_font()

        self.audio_player = audio_player
        self.brightness_control = SettingBrightness(serial_module, self.input_serial)
        self.volume_control = SettingVolume(serial_module, self.input_serial, audio_player)
        self.current_menu_image = None

    def load_font(self):
        font_paths = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",  
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  
        ]
        
        for font_path in font_paths:
            try:
                self.font_path = font_path
                return ImageFont.truetype(font_path, 20)
            except IOError:
                setting_logger.warning(f"Could not load font: {font_path}")
        
        setting_logger.error("Could not load any fonts. Using default font.")
        return ImageFont.load_default()
    
    def check_inputs(self):
        inputs = self.serial_module.get_inputs()
        if inputs and 'result' in inputs:
            result = inputs['result']
            buttons = result['buttons']

            if buttons[3]:  # UP button
                self.selected_item = max(0, self.selected_item - 1)
                self.update_display()
                time.sleep(0.2)
            elif buttons[2]:  # DOWN button
                self.selected_item = min(len(self.menu_items) - 1, self.selected_item + 1)
                self.update_display()
                time.sleep(0.2)
            elif buttons[1]:  # RIGHT button
                if self.selected_item == 0:  # Volume control
                    action, new_volume = self.volume_control.run()
                    if action == 'confirm':
                        self.audio_player.set_audio_volume(new_volume)
                        setting_logger.info(f"Volume updated to {new_volume:.2f}")
                    elif action == 'clean':
                        setting_logger.info(f"Volume Interrupt...")
                        return action
                    else:
                        setting_logger.info("Volume adjustment cancelled")
                    self.update_display()
                if self.selected_item == 1:  # Brightness control
                    action, new_brightness = self.brightness_control.run()
                    if action == 'confirm':
                        self.serial_module.set_brightness(new_brightness)
                        setting_logger.info(f"Brightness updated to {new_brightness:.2f}")
                    elif action == 'clean':
                        setting_logger.info(f"Brightness Interrupt...")
                        return action
                    else:
                        setting_logger.info("Brightness adjustment cancelled")
                    self.update_display()
                if self.selected_item == 4:  # 終了
                    return 'back'
            elif buttons[0]:  # LEFT button
                return 'back'
        return None


    def draw_icon(self, draw, icon, position, icon_color=(255, 255, 255)):
        x, y = position
        size = self.icon_size  

        if icon == 'volume':
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
            ], fill=icon_color)

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
                draw.arc(arc_bbox, start=300, end=60, fill=icon_color, width=2)

        elif icon == 'brightness':
            # Half-filled sun icon
            center = size // 2
            
            # Draw the full circle outline
            draw.ellipse([x+size*0.17, y+size*0.17, x+size*0.83, y+size*0.83], outline=icon_color, width=2)
            
            # Fill the left half of the circle
            draw.pieslice([x+size*0.17, y+size*0.17, x+size*0.83, y+size*0.83], start=90, end=270, fill=icon_color)
            
            # Draw the rays
            for i in range(8):
                angle = i * 45
                x1 = x + center + int(size*0.58 * math.cos(math.radians(angle)))
                y1 = y + center + int(size*0.58 * math.sin(math.radians(angle)))
                x2 = x + center + int(size*0.42 * math.cos(math.radians(angle)))
                y2 = y + center + int(size*0.42 * math.sin(math.radians(angle)))
                draw.line([x1, y1, x2, y2], fill=icon_color, width=2)

        elif icon == 'character':
            # Smiling face icon 
            padding = size * 0.1
            center_x = x + size // 2
            center_y = y + size // 2
            face_radius = (size - 2 * padding) // 2

            # Draw the face outline
            draw.ellipse([x + padding, y + padding, x + size - padding, y + size - padding], outline=icon_color, width=2)

            # Draw eyes 
            eye_radius = size * 0.06
            eye_offset = face_radius * 0.35
            left_eye_center = (center_x - eye_offset, center_y - eye_offset)
            right_eye_center = (center_x + eye_offset, center_y - eye_offset)
            draw.ellipse([left_eye_center[0] - eye_radius, left_eye_center[1] - eye_radius,
                          left_eye_center[0] + eye_radius, left_eye_center[1] + eye_radius], fill=icon_color)
            draw.ellipse([right_eye_center[0] - eye_radius, right_eye_center[1] - eye_radius,
                          right_eye_center[0] + eye_radius, right_eye_center[1] + eye_radius], fill=icon_color)

            # Draw a smile 
            smile_y = center_y + face_radius * 0.1  
            smile_width = face_radius * 0.9  
            smile_height = face_radius * 0.7  
            smile_bbox = [center_x - smile_width/2, smile_y - smile_height/2,
                          center_x + smile_width/2, smile_y + smile_height/2]
            draw.arc(smile_bbox, start=0, end=180, fill=icon_color, width=2)
            
        elif icon == 'settings':
            # Solid gear icon with square teeth
            center = size // 2
            outer_radius = size * 0.45
            num_teeth = 8
            tooth_depth = size * 0.15
            tooth_width = size * 0.12

            # Create a list to hold the points of the gear
            gear_shape = []

            for i in range(num_teeth * 2):
                angle = i * (360 / (num_teeth * 2))
                if i % 2 == 0:
                    # Outer points (teeth)
                    x1 = x + center + outer_radius * math.cos(math.radians(angle - 360/(num_teeth*4)))
                    y1 = y + center + outer_radius * math.sin(math.radians(angle - 360/(num_teeth*4)))
                    x2 = x + center + outer_radius * math.cos(math.radians(angle + 360/(num_teeth*4)))
                    y2 = y + center + outer_radius * math.sin(math.radians(angle + 360/(num_teeth*4)))
                    gear_shape.extend([(x1, y1), (x2, y2)])
                else:
                    # Inner points (between teeth)
                    x1 = x + center + (outer_radius - tooth_depth) * math.cos(math.radians(angle - tooth_width))
                    y1 = y + center + (outer_radius - tooth_depth) * math.sin(math.radians(angle - tooth_width))
                    x2 = x + center + (outer_radius - tooth_depth) * math.cos(math.radians(angle + tooth_width))
                    y2 = y + center + (outer_radius - tooth_depth) * math.sin(math.radians(angle + tooth_width))
                    gear_shape.extend([(x1, y1), (x2, y2)])

            # Draw the gear as a single polygon
            draw.polygon(gear_shape, fill=icon_color)

            # Draw a small circle in the center
            center_radius = size * 0.15
            draw.ellipse([x + center - center_radius, y + center - center_radius,
                          x + center + center_radius, y + center + center_radius],
                         fill=self.background_color)

        elif icon == 'exit':
            # X icon
            draw.line([x+size*0.17, y+size*0.17, x+size*0.83, y+size*0.83], fill=icon_color, width=3)
            draw.line([x+size*0.17, y+size*0.83, x+size*0.83, y+size*0.17], fill=icon_color, width=3)

    def update_display(self):
        # Create setting menu
        image = Image.new('RGB', self.display_size, self.background_color)
        draw = ImageDraw.Draw(image)

        # Drawing highlight
        y_position = 15 + self.selected_item * 40
        draw.rounded_rectangle([45, y_position, 185, y_position+35], radius = 8, fill=self.highlight_color)

        for i, item in enumerate(self.menu_items):
            y_position = 20 + i * 40
            # Choose text and icon color based on whether this item is selected
            selected_color = self.highlight_text_color if i == self.selected_item else self.text_color
            self.draw_icon(draw, item['icon'], (60, y_position), icon_color=selected_color)
            
            draw.text((90, y_position), item['text'], font=self.font, fill=selected_color)
        
        # Draw navigation buttons
        draw.polygon([(20, 120), (30, 110), (30, 130)], fill=self.text_color)  # Left arrow
        draw.polygon([(220, 120), (210, 110), (210, 130)], fill=self.text_color)  # Right arrow
        fixFont = ImageFont.truetype(self.font_path, 12)
        draw.text((20, 135), "戻る", font=fixFont, fill=self.text_color)
        draw.text((200, 135), "決定", font=fixFont, fill=self.text_color)

        self.current_menu_image = image
        
        # Apply current brightness to the image
        enhancer = ImageEnhance.Brightness(image)
        brightened_image = enhancer.enhance(self.serial_module.current_brightness)

        # Convert to bytes and send to display
        img_byte_arr = io.BytesIO()
        brightened_image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        self.serial_module.send_image_data(img_byte_arr)

    def display_menu(self):
        self.update_display()
        while True:
            action = self.check_inputs()
            if action == 'back':
                setting_logger.info("Returning to main app.")
                return 'exit'
            if action == 'clean':
                setting_logger.info("Received clean from actions.")
                return action