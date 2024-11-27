#!/bin/sh

# Set up logging
exec > >(tee -a "/tmp/seaman_ai_speaker.log") 2>&1

echo "Starting AI Speaker System at $(date)"
echo "Current user: $(whoami)"
echo "Current directory: $(pwd)"

# Load environment variables
. /etc/profile.d/seaman_env.sh

# Add system Python packages to PYTHONPATH
export PYTHONPATH="/usr/lib/python3.12/site-packages:$PYTHONPATH"

cleanup() {
    echo "Cleaning up..."
    # Kill any processes using audio devices
    fuser -k /dev/snd/* 2>/dev/null || true
    
    # Remove lock file if it exists
    rm -f /tmp/audio_device.lock
    
    if [ ! -z "$PYTHON_PID" ]; then
        kill -TERM "$PYTHON_PID" 2>/dev/null || true
    fi
    exit 0
}

# Clear any existing audio locks
rm -f /tmp/audio_device.lock
fuser -k /dev/snd/* 2>/dev/null || true
sleep 1

trap cleanup INT TERM

# Activate virtual environment and verify required modules
source .venv/bin/activate --system-site-packages

# Check required modules
echo "Verifying required Python modules..."
python3 -c "
import sys
required_modules = ['pvporcupine', 'pyaudio', 'numpy']
missing_modules = []
for module in required_modules:
    try:
        __import__(module)
        print(f'{module} ✓')
    except ImportError as e:
        missing_modules.append(module)
        print(f'{module} ✗ ({str(e)})')
if missing_modules:
    print('\nMissing modules:', ', '.join(missing_modules))
    sys.exit(1)
print('\nAll required modules are available.')
"
source /etc/profile.d/seaman_env.sh

if [ $? -eq 0 ]; then
    # Ensure audio device is ready
    fuser -k /dev/snd/* 2>/dev/null || true
    sleep 1
    
    python3 main.py &
    PYTHON_PID=$!
    wait $PYTHON_PID
else
    echo "Error: Missing required Python modules. Please install them first."
    exit 1
fi

cleanup