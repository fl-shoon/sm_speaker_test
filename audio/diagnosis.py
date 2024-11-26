import pyaudio
import wave
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_audio_device():
    """Test audio device recording"""
    p = pyaudio.PyAudio()
    
    try:
        # List all devices
        logger.info("\nAvailable audio devices:")
        for i in range(p.get_device_count()):
            try:
                dev_info = p.get_device_info_by_index(i)
                logger.info(f"Device {i}: {dev_info['name']}")
                logger.info(f"  Input channels: {dev_info['maxInputChannels']}")
                logger.info(f"  Sample rate: {dev_info['defaultSampleRate']}")
            except Exception as e:
                logger.error(f"Error getting device info for index {i}: {e}")
        
        # Try to record some audio
        logger.info("\nTesting recording...")
        
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=512,
            input_device_index=0  # Try device 0
        )
        
        frames = []
        for i in range(0, 48):  # Record for ~1.5 seconds
            data = stream.read(512, exception_on_overflow=False)
            frames.append(data)
            logger.info(f"Recorded chunk {i+1}/48")
        
        stream.stop_stream()
        stream.close()
        
        # Save the recording
        logger.info("\nSaving test recording...")
        wf = wave.open("test_recording.wav", 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(16000)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        logger.info("Test completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during test: {e}")
    finally:
        p.terminate()

if __name__ == "__main__":
    test_audio_device()