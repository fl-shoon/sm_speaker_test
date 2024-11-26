import pyaudio
import sys
import time

def diagnose_audio():
    print("\n=== Audio System Diagnostic ===\n")
    
    try:
        print("Initializing PyAudio...")
        p = pyaudio.PyAudio()
        print("PyAudio initialized successfully")
        
        print("\nSystem Information:")
        print(f"PyAudio version: {pyaudio.get_portaudio_version()}")
        print(f"Default input device index: {p.get_default_input_device_info().get('index', 'Unknown')}")
        
        print("\nAvailable Devices:")
        for i in range(p.get_device_count()):
            try:
                dev_info = p.get_device_info_by_index(i)
                print(f"\nDevice {i}:")
                print(f"  Name: {dev_info['name']}")
                print(f"  Input channels: {dev_info['maxInputChannels']}")
                print(f"  Output channels: {dev_info['maxOutputChannels']}")
                print(f"  Default sample rate: {dev_info['defaultSampleRate']}")
                print(f"  Host API: {p.get_host_api_info_by_index(dev_info['hostApi'])['name']}")
            except Exception as e:
                print(f"\nError getting info for device {i}: {e}")
        
        print("\nTesting Audio Stream...")
        # Try to open a test stream
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=512,
                start=False
            )
            print("Stream opened successfully")
            
            stream.start_stream()
            print("Stream started successfully")
            
            print("Testing audio capture...")
            data = stream.read(512, exception_on_overflow=False)
            print(f"Successfully captured {len(data)} bytes of audio data")
            
            stream.stop_stream()
            stream.close()
            print("Stream closed successfully")
        except Exception as e:
            print(f"Error testing stream: {e}")
        
        p.terminate()
        print("\nDiagnostic complete!")
        
    except Exception as e:
        print(f"Error during diagnostic: {e}")

if __name__ == "__main__":
    diagnose_audio()