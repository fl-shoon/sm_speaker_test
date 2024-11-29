from enum import Enum, auto
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from utils.define import *

import asyncio
import logging
import math

logging.basicConfig(level=logging.INFO)
setting_logger = logging.getLogger(__name__)

class SettingState(Enum):
    MAIN_MENU = auto()
    VOLUME = auto()
    BRIGHTNESS = auto()
    CHARACTER = auto()
    SETTINGS = auto()
    EXIT = auto()

class MenuItem:
    def __init__(self, id: SettingState, icon: str, text: str, handler=None):
        self.id = id
        self.icon = icon
        self.text = text
        self.handler = handler

class DisplayTheme:
    """Theme configuration for display elements"""
    def __init__(self):
        self.background_color = (73, 80, 87)
        self.text_color = (255, 255, 255)
        self.highlight_color = (255, 255, 255)
        self.display_size = (240, 240)
        self.highlight_text_color = (0, 0, 0)
        self.icon_size = 24

class SettingMenu:
    def __init__(self, audio_player, display_manager):
        self.display_manager = display_manager
        self.audio_player = audio_player
        
        self.theme = DisplayTheme()
        self.font = ImageFont.truetype(font=NotoSansFont, size=20)
        
        self.menu_items = [
            MenuItem(SettingState.VOLUME, 'volume', '音量', self._handle_volume),
            MenuItem(SettingState.BRIGHTNESS, 'brightness', '輝度', self._handle_brightness),
            MenuItem(SettingState.CHARACTER, 'character', 'キャラ', self._handle_character),
            MenuItem(SettingState.SETTINGS, 'settings', '設定', self._handle_settings),
            MenuItem(SettingState.EXIT, 'exit', '終了', self._handle_exit)
        ]
        
        self.selected_index = 0
        self.current_state = SettingState.MAIN_MENU
        self._transition_lock = asyncio.Lock()

    async def _check_buttons(self):
        buttons = await self.display_manager.server.get_buttons()

        if buttons[2]:  # UP button
            self.selected_index = max(0, self.selected_index - 1)
            await self.update_display()
            await asyncio.sleep(0.2)
        elif buttons[1]:  # DOWN button
            self.selected_index = min(len(self.menu_items) - 1, self.selected_index + 1)
            await self.update_display()
            await asyncio.sleep(0.2)
        elif buttons[0] or buttons[4]:  # Center/Right button
            if self.selected_index == 0:  # Volume setting
                action, new_volume = await self._handle_volume()
                if action == 'confirm':
                    self.audio_player.set_audio_volume(new_volume)
                    setting_logger.info(f"Volume updated to {new_volume:.2f}")
                else:
                    setting_logger.info("Volume adjustment cancelled")
                await self.update_display()
            if self.selected_index == 1:  # Brightness Setting
                action, new_brightness = await self._handle_brightness()
                if action == 'confirm':
                    self.display_manager.set_brightness(new_brightness)
                    setting_logger.info(f"Brightness updated to {new_brightness:.2f}")
                else:
                    setting_logger.info("Brightness adjustment cancelled")
                await self.update_display()
            if self.selected_index == 4:  # 終了
                return 'back'
        elif buttons[3]:  # LEFT button
            return 'back'
        await asyncio.sleep(0.1)
        return None

    async def _handle_volume(self):
        """Volume Setting"""
        self.current_state = SettingState.VOLUME
        original_volume = self.audio_player.current_volume
        temp_volume = original_volume

        await self.update_display(preview_value=temp_volume)

        while True:
            buttons = await self.display_manager.server.get_buttons()
            
            if buttons[2]:  # UP
                temp_volume = min(1.0, temp_volume + 0.05)
                await self.update_display(preview_value=temp_volume)
                await asyncio.sleep(0.2)
            elif buttons[1]:  # DOWN
                temp_volume = max(0.0, temp_volume - 0.05)
                await self.update_display(preview_value=temp_volume)
                await asyncio.sleep(0.2)
            elif buttons[0] or buttons[4]:  # RIGHT/CONFIRM
                self.current_state = SettingState.MAIN_MENU
                return 'confirm', temp_volume
            elif buttons[3]:  # LEFT/BACK
                self.current_state = SettingState.MAIN_MENU
                return 'back', original_volume
            
            await asyncio.sleep(0.1)

    async def _handle_brightness(self):
        """Brightness Setting"""
        self.current_state = SettingState.BRIGHTNESS
        original_brightness = self.display_manager.current_brightness
        temp_brightness = original_brightness
        await self.update_display(preview_value=temp_brightness)

        while True:
            buttons = await self.display_manager.server.get_buttons()
            
            if buttons[2]:  # UP
                temp_brightness = min(1.0, temp_brightness + 0.05)
                await self.update_display(preview_value=temp_brightness)
                await asyncio.sleep(0.2)
            elif buttons[1]:  # DOWN
                temp_brightness = max(0.0, temp_brightness - 0.05)
                await self.update_display(preview_value=temp_brightness)
                await asyncio.sleep(0.2)
            elif buttons[0] or buttons[4]:  # RIGHT/CONFIRM
                self.current_state = SettingState.MAIN_MENU
                return 'confirm', temp_brightness
            elif buttons[3]:  # LEFT/BACK
                self.current_state = SettingState.MAIN_MENU
                return 'back', original_brightness
            
            await asyncio.sleep(0.1)

    async def _handle_character(self):
        """Handle character settings"""
        self.current_state = SettingState.CHARACTER
        # Character settings implementation
        self.current_state = SettingState.MAIN_MENU
        return None

    async def _handle_settings(self):
        """Handle general settings"""
        self.current_state = SettingState.SETTINGS
        # General settings implementation
        self.current_state = SettingState.MAIN_MENU
        return None

    async def _handle_exit(self):
        """Handle exit action"""
        self.current_state = SettingState.EXIT
        return 'exit'
    
    def _draw_icon(self, draw, icon: str, position: tuple, color: tuple = (255, 255, 255)):
        x, y = position
        size = self.theme.icon_size

        if icon == 'volume':
            self._draw_volume_icon(draw, position, color=color)

        elif icon == 'brightness':
            self._draw_brightness_icon(draw, position, color=color)

        elif icon == 'character':
            # Character icon 
            padding = size * 0.1
            center_x = x + size // 2
            center_y = y + size // 2
            face_radius = (size - 2 * padding) // 2
            # Face outline
            draw.ellipse([x + padding, y + padding, x + size - padding, y + size - padding], outline=color, width=2)
            # Eyes 
            eye_radius = size * 0.06
            eye_offset = face_radius * 0.35
            left_eye_center = (center_x - eye_offset, center_y - eye_offset)
            right_eye_center = (center_x + eye_offset, center_y - eye_offset)
            draw.ellipse([left_eye_center[0] - eye_radius, left_eye_center[1] - eye_radius,
                          left_eye_center[0] + eye_radius, left_eye_center[1] + eye_radius], fill=color)
            draw.ellipse([right_eye_center[0] - eye_radius, right_eye_center[1] - eye_radius,
                          right_eye_center[0] + eye_radius, right_eye_center[1] + eye_radius], fill=color)
            # Smile 
            smile_y = center_y + face_radius * 0.1  
            smile_width = face_radius * 0.9  
            smile_height = face_radius * 0.7  
            smile_bbox = [center_x - smile_width/2, smile_y - smile_height/2,
                          center_x + smile_width/2, smile_y + smile_height/2]
            draw.arc(smile_bbox, start=0, end=180, fill=color, width=2)

        elif icon == 'settings':
            # Improved settings gear icon
            center = size // 2
            outer_radius = size * 0.45
            num_teeth = 8
            tooth_depth = size * 0.15
            tooth_width = size * 0.12

            # Create gear shape
            gear_points = []
            for i in range(num_teeth * 2):
                angle = i * (360 / (num_teeth * 2))
                if i % 2 == 0:
                    x1 = x + center + outer_radius * math.cos(math.radians(angle - 360/(num_teeth*4)))
                    y1 = y + center + outer_radius * math.sin(math.radians(angle - 360/(num_teeth*4)))
                    x2 = x + center + outer_radius * math.cos(math.radians(angle + 360/(num_teeth*4)))
                    y2 = y + center + outer_radius * math.sin(math.radians(angle + 360/(num_teeth*4)))
                    gear_points.extend([(x1, y1), (x2, y2)])
                else:
                    x1 = x + center + (outer_radius - tooth_depth) * math.cos(math.radians(angle - tooth_width))
                    y1 = y + center + (outer_radius - tooth_depth) * math.sin(math.radians(angle - tooth_width))
                    x2 = x + center + (outer_radius - tooth_depth) * math.cos(math.radians(angle + tooth_width))
                    y2 = y + center + (outer_radius - tooth_depth) * math.sin(math.radians(angle + tooth_width))
                    gear_points.extend([(x1, y1), (x2, y2)])

            # Draw gear with shadow
            shadow_points = [(x+1, y+1) for x, y in gear_points]
            draw.polygon(shadow_points, fill=(0, 0, 0, 128))
            draw.polygon(gear_points, fill=color)

            # Center circle
            center_radius = size * 0.15
            draw.ellipse([
                x + center - center_radius,
                y + center - center_radius,
                x + center + center_radius,
                y + center + center_radius
            ], fill=self.theme.background_color)

        elif icon == 'exit':
            # Exit icon
            padding = size * 0.17
            shadow_offset = 1

            # Draw shadow
            for offset in [(shadow_offset, shadow_offset)]:
                draw.line([
                    x + padding + offset[0],
                    y + padding + offset[1],
                    x + size - padding + offset[0],
                    y + size - padding + offset[1]
                ], fill=(0, 0, 0, 128), width=3)
                draw.line([
                    x + padding + offset[0],
                    y + size - padding + offset[1],
                    x + size - padding + offset[0],
                    y + padding + offset[1]
                ], fill=(0, 0, 0, 128), width=3)

            # Draw X
            draw.line([
                x + padding,
                y + padding,
                x + size - padding,
                y + size - padding
            ], fill=color, width=3)
            draw.line([
                x + padding,
                y + size - padding,
                x + size - padding,
                y + padding
            ], fill=color, width=3)
    
    async def create_menu_image(self):
        image = Image.new('RGB', self.theme.display_size, self.theme.background_color)
        draw = ImageDraw.Draw(image)

        for i, item in enumerate(self.menu_items):
            y_position = 20 + i * 40
            
            if i == self.selected_index:
                shadow_rect = [44, y_position-1, 186, y_position+36]
                draw.rounded_rectangle(shadow_rect, radius=8, fill=(0, 0, 0, 128))
                
                highlight_rect = [45, y_position, 185, y_position+35]
                draw.rounded_rectangle(highlight_rect, radius=8, fill=self.theme.highlight_color)
            
            color = self.theme.highlight_text_color if i == self.selected_index else self.theme.text_color
            self._draw_icon(draw, item.icon, (60, y_position), color=color)
            draw.text((90, y_position), item.text, font=self.font, fill=color)

        await self._draw_navigation(draw)

        return image

    async def _draw_navigation(self, draw):
        nav_font = ImageFont.truetype(font=NotoSansFont, size=12)
        
        left_arrow = [(20, 120), (30, 110), (30, 130)]
        draw.polygon([(x+1, y+1) for x, y in left_arrow], fill=(0, 0, 0, 128))
        draw.polygon(left_arrow, fill=self.theme.text_color)
        
        right_arrow = [(220, 120), (210, 110), (210, 130)]
        draw.polygon([(x+1, y+1) for x, y in right_arrow], fill=(0, 0, 0, 128))
        draw.polygon(right_arrow, fill=self.theme.text_color)
        
        draw.text((20, 135), "戻る", font=nav_font, fill=self.theme.text_color)
        draw.text((200, 135), "決定", font=nav_font, fill=self.theme.text_color)

    def _draw_brightness_icon(self, draw, position, color=(255, 255, 255)):
        x, y = position
        size = self.theme.icon_size

        # Brightness icon
        center = size // 2
        draw.ellipse([x+size*0.17, y+size*0.17, x+size*0.83, y+size*0.83], outline=color, width=2)
        draw.pieslice([x+size*0.17, y+size*0.17, x+size*0.83, y+size*0.83], start=90, end=270, fill=color)
        
        # Rays
        for i in range(8):
            angle = i * 45
            x1 = x + center + int(size*0.58 * math.cos(math.radians(angle)))
            y1 = y + center + int(size*0.58 * math.sin(math.radians(angle)))
            x2 = x + center + int(size*0.42 * math.cos(math.radians(angle)))
            y2 = y + center + int(size*0.42 * math.sin(math.radians(angle)))
            draw.line([x1, y1, x2, y2], fill=color, width=2)

    def _draw_volume_icon(self, draw, position, color=(255, 255, 255)):
        x, y = position
        size = self.theme.icon_size
        
        speaker_width = size * 0.4
        speaker_height = size * 0.6
        speaker_x = x + (size - speaker_width) // 2
        speaker_y = y + (size - speaker_height) // 2

        # Speaker body
        draw.polygon([
            (speaker_x, speaker_y + speaker_height * 0.3),
            (speaker_x + speaker_width * 0.6, speaker_y + speaker_height * 0.3),
            (speaker_x + speaker_width, speaker_y),
            (speaker_x + speaker_width, speaker_y + speaker_height),
            (speaker_x + speaker_width * 0.6, speaker_y + speaker_height * 0.7),
            (speaker_x, speaker_y + speaker_height * 0.7)
        ], fill=color)

        # Sound waves
        center_x = x + size * 0.7
        center_y = y + size // 2
        for i in range(3):
            radius = size * (0.15 + i * 0.1)
            draw.arc([
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius
            ], start=300, end=60, fill=color, width=2)
    
    async def update_display(self, preview_value=None):
        async with self._transition_lock:
            if self.current_state == SettingState.MAIN_MENU:
                image = await self.create_menu_image()
            elif self.current_state == SettingState.BRIGHTNESS:
                image = await self.create_brightness_image(preview_value)

                if preview_value is not None:
                    enhancer = ImageEnhance.Brightness(image)
                    image = enhancer.enhance(preview_value)
                else:
                    brightened_img = self.display_manager.apply_brightness(image)
            elif self.current_state == SettingState.VOLUME:
                image = await self.create_volume_image(preview_value)
                brightened_img = self.display_manager.apply_brightness(image)
            else:
                image = await self.create_menu_image()

            # brightened_img = self.display_manager.apply_brightness(image)
            encoded_data = self.display_manager.encode_image_to_bytes(brightened_img)
            await self.display_manager.send_image(encoded_data)

    async def create_brightness_image(self, preview_value=None):
        """Brightness Setting UI"""
        image = Image.new('RGB', self.theme.display_size, self.theme.background_color)
        draw = ImageDraw.Draw(image)

        current_value = preview_value if preview_value is not None else self.display_manager.current_brightness

        # Draw brightness icon and text
        icon_x = self.theme.display_size[0] // 2 - self.theme.icon_size // 2
        icon_y = 20
        self._draw_brightness_icon(draw, (icon_x, icon_y))
        
        small_font = ImageFont.truetype(NotoSansFont, 14)
        text = "輝度"
        text_bbox = draw.textbbox((0, 0), text, font=small_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = self.theme.display_size[0] // 2 - text_width // 2
        draw.text((text_x, icon_y + self.theme.icon_size + 5), text, font=small_font, fill=self.theme.text_color)

        # Draw vertical brightness bar
        bar_width = 20
        bar_height = 140
        bar_x = (self.theme.display_size[0] - bar_width) // 2
        bar_y = 80
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], outline=self.theme.text_color)
        filled_height = int(bar_height * current_value)
        draw.rectangle([bar_x, bar_y + bar_height - filled_height, bar_x + bar_width, bar_y + bar_height], 
                    fill=self.theme.highlight_color)

        # Draw slider
        slider_width = 30
        slider_height = 4
        slider_y = bar_y + bar_height - filled_height - slider_height // 2
        draw.rectangle([bar_x - (slider_width - bar_width) // 2, slider_y, 
                    bar_x + bar_width + (slider_width - bar_width) // 2, slider_y + slider_height], 
                    fill=self.theme.text_color)

        # Draw value in circle
        value_size = 30
        value_x = bar_x + bar_width + 20
        value_y = slider_y + slider_height // 2
        draw.ellipse([value_x, value_y - value_size//2, value_x + value_size, value_y + value_size//2], 
                    fill=self.theme.text_color)
        brightness_percentage = int(current_value * 100)
        percentage_font = ImageFont.truetype(NotoSansFont, 14)
        percentage_text = f"{brightness_percentage}"
        text_bbox = draw.textbbox((0, 0), percentage_text, font=percentage_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = value_x + (value_size - text_width) // 2
        text_y = value_y - text_height // 2
        vertical_adjustment = -1  
        text_y += vertical_adjustment
        draw.text((text_x, text_y - 1), percentage_text, font=percentage_font, fill=self.theme.background_color)

        # Draw navigation
        await self._draw_navigation(draw)
        
        return image

    async def create_volume_image(self, preview_value=None):
        """Volume Setting UI"""
        image = Image.new('RGB', self.theme.display_size, self.theme.background_color)
        draw = ImageDraw.Draw(image)

        current_value = preview_value if preview_value is not None else self.audio_player.current_volume

        # Draw volume icon and text
        icon_x = self.theme.display_size[0] // 2 - self.theme.icon_size // 2
        icon_y = 20
        self._draw_volume_icon(draw, (icon_x, icon_y))
        
        small_font = ImageFont.truetype(NotoSansFont, 14)
        text = "音量"
        text_bbox = draw.textbbox((0, 0), text, font=small_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = self.theme.display_size[0] // 2 - text_width // 2
        draw.text((text_x, icon_y + self.theme.icon_size + 5), text, font=small_font, fill=self.theme.text_color)

        # Draw vertical volume bar
        bar_width = 20
        bar_height = 140
        bar_x = (self.theme.display_size[0] - bar_width) // 2
        bar_y = 80
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], outline=self.theme.text_color)
        filled_height = int(bar_height * current_value)
        draw.rectangle([bar_x, bar_y + bar_height - filled_height, bar_x + bar_width, bar_y + bar_height], 
                    fill=self.theme.highlight_color)

        # Draw slider
        slider_width = 30
        slider_height = 4
        slider_y = bar_y + bar_height - filled_height - slider_height // 2
        draw.rectangle([bar_x - (slider_width - bar_width) // 2, slider_y, 
                    bar_x + bar_width + (slider_width - bar_width) // 2, slider_y + slider_height], 
                    fill=self.theme.text_color)

        # Draw value in circle
        value_size = 30
        value_x = bar_x + bar_width + 20
        value_y = slider_y + slider_height // 2
        draw.ellipse([value_x, value_y - value_size//2, value_x + value_size, value_y + value_size//2], 
                    fill=self.theme.text_color)
        volume_percentage = int(current_value * 100)
        percentage_font = ImageFont.truetype(NotoSansFont, 14)
        percentage_text = f"{volume_percentage}"
        text_bbox = draw.textbbox((0, 0), percentage_text, font=percentage_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = value_x + (value_size - text_width) // 2
        text_y = value_y - text_height // 2
        vertical_adjustment = -1  
        text_y += vertical_adjustment
        draw.text((text_x, text_y - 1), percentage_text, font=percentage_font, fill=self.theme.background_color)

        # Draw navigation
        await self._draw_navigation(draw)
        
        return image
    
    async def display_menu(self):
        await self.update_display()
        while True:
            action = await self._check_buttons()
            if action == 'back':
                setting_logger.info("Returning to main app.")
                return 'exit'