import pyaudio
import wave
import time
import os

def test_audio():
    print("\nTesting audio setup...")
    
    # Check device presence
    if not os.path.exists('/dev/snd/pcmC0D0c'):
        print("Audio capture device not found!")
        return
    
    # Force release any existing handles
    os.system('fuser -k /dev/snd/*')
    time.sleep(1)
    
    p = None
    stream = None
    
    try:
        print("Initializing PyAudio...")
        p = pyaudio.PyAudio()
        
        # Find USB CODEC device
        device_index = None
        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                print(f"Found device {i}: {info['name']}")
                if info['maxInputChannels'] > 0:
                    if 'CODEC' in info['name'] or 'USB' in info['name']:
                        device_index = i
                        print(f"Selected device {i}: {info['name']}")
                        break
            except:
                continue
        
        if device_index is None:
            print("Using default device 0")
            device_index = 0
        
        print("Opening audio stream...")
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=512,
            input_device_index=device_index
        )
        
        print("Recording 3 seconds of audio...")
        frames = []
        for _ in range(94):  # ~3 seconds
            data = stream.read(512, exception_on_overflow=False)
            frames.append(data)
        
        print("Saving recording...")
        with wave.open("test.wav", 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(b''.join(frames))
        
        print("Test completed successfully!")
        
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        if p:
            p.terminate()

if __name__ == "__main__":
    test_audio()