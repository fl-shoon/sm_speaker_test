import argparse
import logging
import os
import signal
import sys
import pyaudio
import struct
import time
from threading import Event
from utils.define import *

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

    def initialize(self):
        """Initialize PicoVoice and audio stream with explicit channel configuration"""
        try:
            import pvporcupine
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                model_path=self.model_path,
                keyword_paths=self.keyword_paths,
                sensitivities=self.sensitivities
            )

            self.audio = pyaudio.PyAudio()
            
            # Find the USB Audio CODEC device
            device_index = None
            device_info = None
            
            # First try to find by name
            for i in range(self.audio.get_device_count()):
                info = self.audio.get_device_info_by_index(i)
                logger.info(f"Checking device {i}: {info['name']}")
                if 'USB AUDIO  CODEC' in info['name']:
                    device_index = i
                    device_info = info
                    break
            
            if device_index is None:
                logger.error("Could not find USB Audio CODEC device")
                return False

            logger.info(f"Selected device info: {device_info}")
            
            # Configure audio stream with explicit parameters for mono input
            try:
                self.audio_stream = self.audio.open(
                    rate=int(self.porcupine.sample_rate),  # Explicit integer conversion
                    channels=1,  # Mono input
                    format=pyaudio.paInt16,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self.porcupine.frame_length,
                    start=False,  # Don't start the stream yet
                )
                
                # Try to start the stream explicitly
                self.audio_stream.start_stream()
                
                logger.info("Audio stream initialized and started successfully")
                return True

            except Exception as audio_error:
                logger.error(f"Error configuring audio stream: {audio_error}")
                
                # Try alternate configuration if the first attempt failed
                try:
                    logger.info("Trying alternate audio configuration...")
                    self.audio_stream = self.audio.open(
                        rate=int(self.porcupine.sample_rate),
                        channels=1,
                        format=pyaudio.paInt16,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=1024,  # Use a standard buffer size
                        stream_callback=None
                    )
                    
                    logger.info("Alternate audio configuration successful")
                    return True
                    
                except Exception as alt_error:
                    logger.error(f"Alternate configuration failed: {alt_error}")
                    return False

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            self.cleanup()
            return False

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

    def run(self):
        """Main detection loop"""
        try:
            logger.info("Starting wake word detection...")
            logger.info("Listening for wake words. Press Ctrl+C to exit.")

            while not exit_event.is_set():
                # Read audio frame
                pcm = self.audio_stream.read(self.porcupine.frame_length, exception_on_overflow=False)
                pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)

                # Process audio frame
                keyword_index = self.porcupine.process(pcm)
                
                # Wake word detected
                if keyword_index >= 0:
                    keyword_name = os.path.basename(self.keyword_paths[keyword_index]).replace('.ppn', '')
                    logger.info(f"Wake word detected: {keyword_name}")
                    
                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Stopping wake word detection...")
        except Exception as e:
            logger.error(f"Error in detection loop: {e}")
        finally:
            self.cleanup()

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
                      default=[0.5, 0.5])
    parser.add_argument('--list-devices', action='store_true',
                      help='List all available audio devices and exit')
    parser.add_argument('--device-index', type=int,
                      help='Specify input device index to use')

    args = parser.parse_args()

    # List devices if requested
    if args.list_devices:
        list_audio_devices()
        sys.exit(0)

    # Validate sensitivities
    if len(args.sensitivities) != len(args.keyword_paths):
        args.sensitivities = [0.5] * len(args.keyword_paths)
        logger.warning(f"Using default sensitivity of 0.5 for all {len(args.keyword_paths)} keywords")

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

    if tester.initialize():
        tester.run()
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()