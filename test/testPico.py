import argparse
import logging
import numpy as np
import os
import signal
import sys
import pvporcupine
import pyaudio
import time
from threading import Event
# from utils.define import *

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
ASSETS_DIR = os.path.join(PARENT_DIR, 'assets')
VOICE_TRIGGER_DIR = os.path.join(ASSETS_DIR, 'trigger')
PicoLangModel = os.path.join(VOICE_TRIGGER_DIR,"pico_voice_language_model_ja.pv")
PicoWakeWordKonnichiwa = os.path.join(VOICE_TRIGGER_DIR,"pico_voice_wake_word_konnichiwa.ppn") 
PicoWakeWordSatoru = os.path.join(VOICE_TRIGGER_DIR,"pico_voice_wake_word_satoru.ppn") 

# Global exit event for graceful shutdown
exit_event = Event()

def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown"""
    logger.info(f"Received signal {signum}")
    exit_event.set()

def list_audio_devices():
    """List all available audio devices"""
    p = pyaudio.PyAudio()
    info = []
    
    logger.info("Available audio devices:")
    for i in range(p.get_device_count()):
        try:
            device_info = p.get_device_info_by_index(i)
            info.append(device_info)
            logger.info(f"Device {i}: {device_info['name']}")
            logger.info(f"  Input channels: {device_info['maxInputChannels']}")
            logger.info(f"  Output channels: {device_info['maxOutputChannels']}")
            logger.info(f"  Default sample rate: {device_info['defaultSampleRate']}")
            logger.info("---")
        except Exception as e:
            logger.error(f"Error getting device info for index {i}: {e}")
    
    p.terminate()
    return info

class PicoVoiceTester:
    def __init__(self, access_key, model_path, keyword_paths, sensitivities, device_index=None):
        self.access_key = access_key
        self.model_path = model_path
        self.keyword_paths = keyword_paths
        self.sensitivities = sensitivities
        self.device_index = device_index
        self.porcupine = None
        self.audio = None
        self.audio_stream = None
        self.gain = 5  # Amplification factor

    def preprocess_audio(self, audio_data):
        """Preprocess audio data with gain and normalization"""
        # Convert to float32 for processing
        float_data = audio_data.astype(np.float32) / 32768.0
        
        # Apply gain
        float_data = float_data * self.gain
        
        # Clip to prevent overflow
        float_data = np.clip(float_data, -1.0, 1.0)
        
        # Convert back to int16
        return (float_data * 32767).astype(np.int16)

    def resample_audio(self, audio_data, orig_rate, new_rate):
        """Improved resampling using linear interpolation"""
        # Calculate resampling parameters
        duration = len(audio_data) / orig_rate
        time_old = np.linspace(0, duration, len(audio_data))
        time_new = np.linspace(0, duration, int(len(audio_data) * new_rate / orig_rate))
        
        # Perform linear interpolation
        resampled = np.interp(time_new, time_old, audio_data)
        return resampled.astype(np.int16)

    def initialize(self):
        try:
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                model_path=self.model_path,
                keyword_paths=self.keyword_paths,
                sensitivities=self.sensitivities
            )
            
            self.audio = pyaudio.PyAudio()
            
            # Find suitable input device
            device_index = self.device_index if self.device_index is not None else self.find_input_device()
            device_info = self.audio.get_device_info_by_index(device_index)
            
            native_sample_rate = int(device_info['defaultSampleRate'])
            logger.info(f"Device native sample rate: {native_sample_rate}")
            logger.info(f"Porcupine required rate: {self.porcupine.sample_rate}")
            
            # Use a larger buffer size to ensure enough data
            buffer_size = self.porcupine.frame_length * 2
            
            try:
                self.audio_stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.porcupine.sample_rate,  # Use Porcupine's rate directly
                    input=True,
                    frames_per_buffer=buffer_size,
                    input_device_index=device_index,
                    stream_callback=None,
                    start=False
                )
                
                self.audio_stream.start_stream()
                logger.info(f"Successfully opened and started device {device_index}")
                
                if self.audio_stream.is_active():
                    logger.info("Audio stream is active")
                    return True
                else:
                    logger.error("Audio stream is not active")
                    return False
                    
            except Exception as e:
                logger.error(f"Failed to open device {device_index}: {e}")
                return False

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            self.cleanup()
            return False

    def calculate_rms(self, data):
        """Safely calculate RMS value"""
        # Ensure we're working with float data
        float_data = data.astype(np.float32) / 32768.0
        
        # Calculate RMS safely
        square_sum = np.sum(float_data ** 2)
        if square_sum > 0:
            return np.sqrt(square_sum / len(float_data)) * 100  # Scale to percentage
        return 0.0

    def run(self):
        try:
            logger.info("Starting wake word detection...")
            logger.info("Listening for wake words. Press Ctrl+C to exit.")
            
            frame_count = 0
            monitor_interval = 50
            silence_threshold = 1.0  # Adjusted threshold for percentage scale
            
            while not exit_event.is_set():
                try:
                    # Read audio frame
                    pcm = self.audio_stream.read(self.porcupine.frame_length, exception_on_overflow=False)
                    pcm_data = np.frombuffer(pcm, dtype=np.int16)
                    
                    # Apply preprocessing
                    pcm_data = self.preprocess_audio(pcm_data)
                    
                    # Monitor audio levels
                    frame_count += 1
                    if frame_count % monitor_interval == 0:
                        rms = self.calculate_rms(pcm_data)
                        peak = np.max(np.abs(pcm_data)) / 32768.0 * 100  # Convert to percentage
                        logger.info(f"Audio levels - RMS: {rms:.2f}%, Peak: {peak:.2f}%")
                        
                        if rms < silence_threshold:
                            logger.warning("Low audio level detected - adjust microphone volume")
                    
                    # Process with Porcupine
                    if len(pcm_data) >= self.porcupine.frame_length:
                        keyword_index = self.porcupine.process(pcm_data[:self.porcupine.frame_length])
                        if keyword_index >= 0:
                            keyword_name = os.path.basename(self.keyword_paths[keyword_index]).replace('.ppn', '')
                            logger.info(f"Wake word detected: {keyword_name}")
                    
                    time.sleep(0.01)

                except Exception as loop_error:
                    logger.error(f"Error in detection loop iteration: {loop_error}", exc_info=True)
                    continue

        except KeyboardInterrupt:
            logger.info("Stopping wake word detection...")
        except Exception as e:
            logger.error(f"Error in main detection loop: {e}", exc_info=True)
        finally:
            self.cleanup()

    def find_input_device(self):
        """Find a suitable input device"""
        p = pyaudio.PyAudio()
        default_input = p.get_default_input_device_info()
        logger.info(f"Default input device: {default_input['name']}")
        
        # If device_index is specified, validate it
        if self.device_index is not None:
            try:
                device_info = p.get_device_info_by_index(self.device_index)
                if device_info['maxInputChannels'] > 0:
                    logger.info(f"Using specified input device: {device_info['name']}")
                    p.terminate()
                    return self.device_index
            except Exception as e:
                logger.error(f"Error with specified device index {self.device_index}: {e}")
        
        # Find the first available input device
        for i in range(p.get_device_count()):
            try:
                device_info = p.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    logger.info(f"Selected input device: {device_info['name']}")
                    p.terminate()
                    return i
            except Exception as e:
                continue
        
        p.terminate()
        raise RuntimeError("No suitable input device found")
    
    def cleanup(self):
        """Cleanup resources with enhanced error handling"""
        logger.info("Starting cleanup process...")
        
        if self.audio_stream is not None:
            try:
                if self.audio_stream.is_active():
                    self.audio_stream.stop_stream()
                self.audio_stream.close()
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
            self.audio_stream = None

        if self.audio is not None:
            try:
                self.audio.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")
            self.audio = None

        if self.porcupine is not None:
            try:
                self.porcupine.delete()
            except Exception as e:
                logger.error(f"Error deleting Porcupine instance: {e}")
            self.porcupine = None

        logger.info("Cleanup process completed")

def main():
    parser = argparse.ArgumentParser(description='PicoVoice Wake Word Tester')
    
    parser.add_argument('--access_key',
                      help='AccessKey obtained from Picovoice Console',
                      default=os.environ.get("PICO_ACCESS_KEY"))
    parser.add_argument('--model_path',
                      help='Path to the Porcupine model file',
                      default=PicoLangModel)
    parser.add_argument('--keyword_paths', nargs='+',
                      help='Paths to keyword model files',
                      default=[PicoWakeWordKonnichiwa, PicoWakeWordSatoru])
    parser.add_argument('--sensitivities', nargs='+', type=float,
                      help='Detection sensitivity for each wake word (between 0 and 1)',
                      default=[0.9, 0.9])  # Increased default sensitivity
    parser.add_argument('--list-devices', action='store_true',
                      help='List all available audio devices and exit')
    parser.add_argument('--device-index', type=int,
                      help='Specify input device index to use')
    parser.add_argument('--gain', type=float,
                      help='Audio gain multiplier',
                      default=5.0)

    args = parser.parse_args()

    if args.list_devices:
        list_audio_devices()
        sys.exit(0)

    # Validate sensitivities
    if len(args.sensitivities) != len(args.keyword_paths):
        args.sensitivities = [0.9] * len(args.keyword_paths)
        logger.warning(f"Using high sensitivity of 0.9 for all {len(args.keyword_paths)} keywords")

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize and run tester
    tester = PicoVoiceTester(
        access_key=args.access_key,
        model_path=args.model_path,
        keyword_paths=args.keyword_paths,
        sensitivities=args.sensitivities,
        device_index=args.device_index
    )
    tester.gain = args.gain

    if tester.initialize():
        tester.run()
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()