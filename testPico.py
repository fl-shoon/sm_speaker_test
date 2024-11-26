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

class PicoVoiceTester:
    def __init__(self, access_key, model_path, keyword_paths, sensitivities):
        self.access_key = access_key
        self.model_path = model_path
        self.keyword_paths = keyword_paths
        self.sensitivities = sensitivities
        self.porcupine = None
        self.audio = None
        self.audio_stream = None

    def initialize(self):
        """Initialize PicoVoice and audio stream"""
        try:
            import pvporcupine
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                model_path=self.model_path,
                keyword_paths=self.keyword_paths,
                sensitivities=self.sensitivities
            )

            self.audio = pyaudio.PyAudio()
            self.audio_stream = self.audio.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length
            )

            logger.info("PicoVoice and audio stream initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            self.cleanup()
            return False

    def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up resources...")
        
        if self.audio_stream is not None:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.audio_stream = None

        if self.audio is not None:
            self.audio.terminate()
            self.audio = None

        if self.porcupine is not None:
            self.porcupine.delete()
            self.porcupine = None

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
    
    parser.add_argument('--access_key', required=True,
                      help='AccessKey obtained from Picovoice Console',
                      default=os.environ.get("PICO_ACCESS_KEY"))
    parser.add_argument('--model_path', required=True,
                      help='Path to the Porcupine model file',
                      default=PicoLangModel)
    parser.add_argument('--keyword_paths', required=True, nargs='+',
                      help='Paths to keyword model files',
                      default=[PicoWakeWordKonnichiwa, PicoWakeWordSatoru])
    parser.add_argument('--sensitivities', nargs='+', type=float,
                      help='Detection sensitivity for each wake word (between 0 and 1)',
                      default=[0.5, 0.5])

    args = parser.parse_args()

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
        sensitivities=args.sensitivities
    )

    if tester.initialize():
        tester.run()
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()