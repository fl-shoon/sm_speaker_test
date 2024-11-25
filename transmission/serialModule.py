from utils.define import BautRate, MCUPort
from PIL import Image, ImageEnhance

import json
import io
import logging
import numpy as np
import serial
import time

logging.basicConfig(level=logging.INFO)
serial_logger = logging.getLogger(__name__)

class SerialModule:
    def __init__(self):
        self.isPortOpen = False
        self.baud_rate = BautRate
        self.comm = None
        self.current_brightness = 1.0  
        self.current_image = None
        self.input_serial = serial.Serial(MCUPort, BautRate, timeout=1)

    def set_brightness(self, brightness):
        self.current_brightness = max(0.0, min(1.0, brightness))

    def open(self, tty):
        try:
            self.comm = serial.Serial(tty, self.baud_rate, timeout=0.1)
            self.isPortOpen = True
            serial_logger.info(f"Port opened successfully at {self.baud_rate} baud")
        except Exception as e:
            self.isPortOpen = False
            serial_logger.warning(f"Failed to open port: {e}")
        return self.isPortOpen

    def send_mcu_command(self, method, params=None):
        serial_connection = self.input_serial  
        
        message = {"method": method}
        if params:
            message["params"] = params
        
        serial_connection.write(json.dumps(message).encode() + b'\n')
        try:
            response = serial_connection.readline().decode().strip()
            
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                serial_logger.error(f"Failed to parse response: {response}")
                return None
        except serial.SerialException as e:
            serial_logger.error(f"Serial communication error: {e}")
            return None
        except Exception as e:
            serial_logger.error(f"Unexpected error in get_inputs: {e}")
            return None

    def send(self, data):
        self.comm.write(data)

    def get_inputs(self):
        return self.send_mcu_command("getInputs")

    def send_text(self):
        self.send('test'.encode())
        time.sleep(0.01)
        self.comm.read_all()

    def send_image_data(self, img_data, timeout=5, retries=3):
        if not self.isPortOpen or self.comm is None:
            serial_logger.warning("Serial port is not open")
            return False

        for attempt in range(retries):
            try:
                self.send_text()
                self.comm.read_all()  # Clear any remaining data
                
                start_time = time.time()
                bytes_written = self.comm.write(img_data)
                write_time = time.time() - start_time
                
                self.comm.flush()  # Ensure all data is written
                
                # Wait for response with timeout
                response_start_time = time.time()
                while time.time() - response_start_time < timeout:
                    if self.comm.in_waiting:
                        self.comm.read_all()
                        return True
                    time.sleep(0.1)
                
                serial_logger.info(f"No response received within {timeout} seconds")
                
            except serial.SerialTimeoutException:
                serial_logger.warning(f"Timeout occurred while writing image data (attempt {attempt + 1}/{retries})")
            except Exception as e:
                serial_logger.warning(f"Error in send_image_data: {str(e)} (attempt {attempt + 1}/{retries})")
            
            if attempt < retries - 1:
                serial_logger.info("Retrying...")
                time.sleep(1)
        
        serial_logger.warning("Failed to send image data after all retries")
        return False

    def fade_image(self, image_path, fade_in=True, steps=20):
        img = Image.open(image_path)
        width, height = img.size

        for i in range(steps):
            if fade_in:
                alpha = int(255 * (i + 1) / steps)
            else:
                alpha = int(255 * (steps - i) / steps)

            faded_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            faded_img.paste(img, (0, 0))
            faded_img.putalpha(alpha)

            rgb_img = Image.new("RGB", faded_img.size, (0, 0, 0))
            rgb_img.paste(faded_img, mask=faded_img.split()[3])

            img_byte_arr = io.BytesIO()
            rgb_img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

            success = self.send_image_data(img_byte_arr)
            if not success:
                serial_logger.warning(f"Failed to send image for step {i+1}, continuing to next step")
            
            time.sleep(0.05) 

    def apply_brightness(self, img):
        enhancer = ImageEnhance.Brightness(img)
        return enhancer.enhance(self.current_brightness)
    
    def send_white_frames(self, flash_delay=0.01, timeout=2):
        white_frame = np.full((240, 240, 3), 255, dtype=np.uint8)
        white_frame_bytes = self.frame_to_bytes(white_frame)

        try:
            # serial_logger.info(f"Attempt {attempt + 1}/{max_retries} to send white frame")
            start_time = time.time()
            
            # Clear any existing data in the serial buffer
            self.comm.reset_input_buffer()
            self.comm.reset_output_buffer()
            
            # Send a small test message
            self.comm.write(b'TEST')
            time.sleep(0.1)
            self.comm.read_all()

            # Send the actual white frame data
            self.comm.write(white_frame_bytes)
            self.comm.flush()

            # Wait for acknowledgment with timeout
            ack_received = False
            while time.time() - start_time < timeout:
                if self.comm.in_waiting:
                    ack_received = True
                    break
                time.sleep(0.1)

            if ack_received:
                time.sleep(flash_delay)
                return True
            else:
                serial_logger.info(f"Failed to turn screen into white within {timeout} seconds")

        except Exception as e:
            serial_logger.warning(f"Error in turning white screen: {str(e)}")

        serial_logger.warning("Failed to send white frames after all retries")
        return False

    def prepare_gif(self, gif_path, target_size=(240, 240)):
        gif = Image.open(gif_path)
        frames = []
        try:
            while True:
                gif.seek(gif.tell() + 1)
                frame = gif.copy().convert('RGB').resize(target_size)
                frames.append(np.array(frame))
        except EOFError:
            pass  
        return frames

    def frame_to_bytes(self, frame):
        img = Image.fromarray(frame)
        brightened_img = self.apply_brightness(img)
        img_byte_arr = io.BytesIO()
        brightened_img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()

    def precompute_frames(self, frames):
        return [self.frame_to_bytes(frame) for frame in frames]

    def fade_image(self, image_path, fade_in=True, steps=20):
        img = Image.open(image_path)
        width, height = img.size

        for i in range(steps):
            if fade_in:
                alpha = int(255 * (i + 1) / steps)
            else:
                alpha = int(255 * (steps - i) / steps)

            faded_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            faded_img.paste(img, (0, 0))
            faded_img.putalpha(alpha)

            rgb_img = Image.new("RGB", faded_img.size, (0, 0, 0))
            rgb_img.paste(faded_img, mask=faded_img.split()[3])

            img_byte_arr = io.BytesIO()
            rgb_img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

            self.send_image_data(img_byte_arr)
            time.sleep(0.001)  
            
    def animate_gif(self, gif_path, frame_delay=0.1):
        frames = self.prepare_gif(gif_path)
        all_frames = self.precompute_frames(frames)
        
        while True:
            for frame_bytes in all_frames:
                self.send_image_data(frame_bytes)
                time.sleep(frame_delay)

    def set_current_image(self, image):
        self.current_image = image

    def set_brightness_image(self, brightness, steps=10, transition_time=0.5):
        if not self.isPortOpen or self.comm is None:
            serial_logger.error("Serial port is not open")
            return False

        if self.current_image is None:
            serial_logger.error("No current image to adjust brightness")
            return False

        start_brightness = self.current_brightness
        brightness_step = (brightness - start_brightness) / steps
        step_time = transition_time / steps

        for i in range(steps + 1):
            current_step_brightness = start_brightness + brightness_step * i
            try:
                # Adjust image brightness
                enhancer = ImageEnhance.Brightness(self.current_image)
                adjusted_image = enhancer.enhance(current_step_brightness)

                # Convert to bytes
                img_byte_arr = io.BytesIO()
                adjusted_image.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()

                # Send to display
                self.send_image_data(img_byte_arr)
                
                serial_logger.debug(f"Adjusted brightness to {current_step_brightness:.2f}")
                time.sleep(step_time)

            except Exception as e:
                serial_logger.error(f"Error adjusting brightness: {str(e)}")
                return False

        self.current_brightness = brightness
        serial_logger.info(f"Brightness adjustment completed. Final brightness: {brightness:.2f}")
        return True

    def close(self):
        if self.isPortOpen and self.comm is not None:
            self.comm.close()
            self.input_serial.close()
            self.isPortOpen = False
            serial_logger.info("Serial connection closed")