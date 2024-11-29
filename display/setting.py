# from display.brightness import SettingBrightness
# from display.volume import SettingVolume
from enum import Enum, auto
from PIL import Image, ImageDraw, ImageFont
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

        self.brightness_control = None
        self.volume_control = None

        # self.brightness_control = SettingBrightness(display_manager=display_manager)
        # self.volume_control = SettingVolume(display_manager=display_manager, audio_player=audio_player)
    
    async def _check_buttons(self):
        buttons = await self.display_manager.server.get_buttons()
        setting_logger.info(f"buttons: {buttons}")

        if buttons[2]:  # UP button
            self.selected_item = max(0, self.selected_item - 1)
            self.create_menu_display()
            await asyncio.sleep(0.2)
        elif buttons[1]:  # DOWN button
            self.selected_item = min(len(self.menu_items) - 1, self.selected_item + 1)
            self.create_menu_display()
            await asyncio.sleep(0.2)
        elif buttons[0] or buttons[4]:  # Center button or Right button
            if self.selected_item == 0:  # Volume control
                # action, new_volume = self.volume_control.run()
                # if action == 'confirm':
                #     self.audio_player.set_audio_volume(new_volume)
                #     setting_logger.info(f"Volume updated to {new_volume:.2f}")
                # elif action == 'clean':
                #     setting_logger.info(f"Volume Interrupt...")
                #     return action
                # else:
                #     setting_logger.info("Volume adjustment cancelled")
                self.create_menu_display()
            if self.selected_item == 1:  # Brightness control
                # action, new_brightness = self.brightness_control.run()
                # if action == 'confirm':
                #     self.serial_module.set_brightness(new_brightness)
                #     setting_logger.info(f"Brightness updated to {new_brightness:.2f}")
                # elif action == 'clean':
                #     setting_logger.info(f"Brightness Interrupt...")
                #     return action
                # else:
                #     setting_logger.info("Brightness adjustment cancelled")
                self.create_menu_display()
            if self.selected_item == 4:  # 終了
                return 'back'
        elif buttons[3]:  # LEFT button
            return 'back'
        await asyncio.sleep(0.1)
        return None

    async def _handle_volume(self):
        """Handle volume adjustment"""
        self.current_state = SettingState.VOLUME
        action, new_volume = await self.volume_control.run()
        if action == 'confirm':
            await self.audio_player.set_volume(new_volume)
            setting_logger.info(f"Volume updated to {new_volume:.2f}")
        elif action == 'clean':
            setting_logger.info("Volume adjustment interrupted")
            return action
        
        self.current_state = SettingState.MAIN_MENU
        await self.update_display()
        return None

    async def _handle_brightness(self):
        """Handle brightness adjustment"""
        self.current_state = SettingState.BRIGHTNESS
        action, new_brightness = await self.brightness_control.run()
        if action == 'confirm':
            await self.display_manager.set_brightness(new_brightness)
            setting_logger.info(f"Brightness updated to {new_brightness:.2f}")
        elif action == 'clean':
            setting_logger.info("Brightness adjustment interrupted")
            return action
            
        self.current_state = SettingState.MAIN_MENU
        await self.update_display()
        return None

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
            # Volume icon 
            icon_width = size * 0.9  
            icon_height = size * 0.9  
            speaker_width = icon_width * 0.4
            speaker_height = icon_height * 0.6

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
                draw.arc(arc_bbox, start=300, end=60, fill=color, width=2)

        elif icon == 'brightness':
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
            # Setting gear icon 
            center = size // 2
            outer_radius = size * 0.45
            num_teeth = 8
            tooth_depth = size * 0.15
            tooth_width = size * 0.12

            # Create a gear shape
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

            # Gear Shadow
            draw.polygon(gear_shape, fill=color)

            # Center circle
            center_radius = size * 0.15
            draw.ellipse([x + center - center_radius, y + center - center_radius,
                          x + center + center_radius, y + center + center_radius],
                         fill=self.theme.background_color)

        elif icon == 'exit':
            # X icon
            draw.line([x+size*0.17, y+size*0.17, x+size*0.83, y+size*0.83], fill=color, width=3)
            draw.line([x+size*0.17, y+size*0.83, x+size*0.83, y+size*0.17], fill=color, width=3)

    async def create_menu_display(self):
        image = Image.new('RGB', self.theme.display_size, self.theme.background_color)
        draw = ImageDraw.Draw(image)

        y_position = 15 + self.selected_index * 40
        draw.rounded_rectangle([45, y_position, 185, y_position+35], radius = 8, fill=self.theme.highlight_color)
        
        for i, item in enumerate(self.menu_items):
            y_position = 20 + i * 40
            color = self.theme.highlight_text_color if i == self.selected_index else self.theme.text_color
            self._draw_icon(draw, item.icon, (60, y_position), color=color)
            draw.text((90, y_position), item.text, font=self.font, fill=color)

        await self._draw_navigation(draw)

        brightened_img = self.display_manager.apply_brightness(image)
        encoded_data = self.display_manager.encode_image_to_bytes(brightened_img)
        await self.display_manager.send_image(encoded_data)
    
    async def _draw_navigation(self, draw):
        """Draw navigation elements"""
        nav_font = ImageFont.truetype(font=NotoSansFont, size=12)
        
        draw.polygon([(20, 120), (30, 110), (30, 130)], fill=self.theme.text_color)  # Left arrow
        draw.polygon([(220, 120), (210, 110), (210, 130)], fill=self.theme.text_color)  # Right arrow
        draw.text((20, 135), "戻る", font=nav_font, fill=self.theme.text_color)
        draw.text((200, 135), "決定", font=nav_font, fill=self.theme.text_color)

    async def display_menu(self):
        await self.create_menu_display()
        while True:
            action = await self._check_buttons()
            if action == 'back':
                setting_logger.info("Returning to main app.")
                return 'exit'
            if action == 'clean':
                setting_logger.info("Received keyboard interrupt from actions.")
                return action