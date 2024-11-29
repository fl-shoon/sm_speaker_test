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
    echo "Starting cleanup process..."
    
    # Kill any processes using audio devices first
    echo "Cleaning up audio devices..."
    fuser -k /dev/snd/* 2>/dev/null || true
    
    # Remove lock file if it exists
    rm -f /tmp/audio_device.lock
    
    if [ ! -z "$PYTHON_PID" ]; then
        echo "Sending termination signal to Python process..."
        kill -TERM "$PYTHON_PID" 2>/dev/null || true
        
        # Give Python time to clean up
        echo "Waiting for Python cleanup (max 10 seconds)..."
        for i in {1..10}; do
            if ! kill -0 "$PYTHON_PID" 2>/dev/null; then
                echo "Python process finished cleanup"
                break
            fi
            sleep 1
        done
        
        # Force kill if still running
        if kill -0 "$PYTHON_PID" 2>/dev/null; then
            echo "Python process still running, forcing termination..."
            kill -9 "$PYTHON_PID" 2>/dev/null || true
        fi
    fi
    
    # Final cleanup of any remaining audio processes
    echo "Final audio cleanup..."
    fuser -k /dev/snd/* 2>/dev/null || true
    pulseaudio --kill 2>/dev/null || true
    
    echo "Cleanup completed"
    exit 0
}

# Clear any existing audio locks
rm -f /tmp/audio_device.lock
fuser -k /dev/snd/* 2>/dev/null || true
sleep 1

trap cleanup SIGINT SIGTERM SIGQUIT

# Activate virtual environment and verify required modules
source .venv/bin/activate --system-site-packages

run_with_monitoring() {
    python3 main.py &
    PYTHON_PID=$!
    
    # Monitor the Python process
    while kill -0 $PYTHON_PID 2>/dev/null; do
        sleep 1
    done
    
    wait $PYTHON_PID
    return $?
}

MAX_RETRIES=3
RETRY_COUNT=0

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

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "Starting AI Speaker System..."
    
    run_with_monitoring
    EXIT_CODE=$?
    
    case $EXIT_CODE in
        0)
            echo "Program completed successfully"
            break
            ;;
        130|131|143)  # SIGINT, SIGTERM, SIGQUIT
            echo "Program received termination signal"
            cleanup
            break
            ;;
        *)
            echo "Program crashed with exit code $EXIT_CODE"
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
                echo "Retrying in 5 seconds..."
                sleep 5
            fi
            ;;
    esac
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Failed to load app. Exiting..."
fi

cleanup