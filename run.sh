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
    echo "Starting cleanup process... (PID: $$)"
    
    if [ ! -z "$PYTHON_PID" ]; then
        echo "Sending graceful termination signal to Python process (PID: $PYTHON_PID)..."

        kill -TERM -"$PYTHON_PID" 2>/dev/null || true
        
        # Give Python more time to clean up display and other resources
        echo "Waiting for Python cleanup (max 30 seconds)..."
        cleanup_timeout=30
        while [ $cleanup_timeout -gt 0 ]; do
            if ! kill -0 "$PYTHON_PID" 2>/dev/null; then
                echo "Python process finished cleanup"
                break
            fi
            cleanup_timeout=$((cleanup_timeout - 1))
            sleep 1
        done
        
        # Only after Python cleanup, handle audio devices
        echo "Cleaning up audio devices..."
        fuser -k /dev/snd/* 2>/dev/null || true
        
        if kill -0 "$PYTHON_PID" 2>/dev/null; then
            echo "Python process still running, forcing termination..."
            kill -9 -"$PYTHON_PID" 2>/dev/null || true  
            sleep 1
        fi
    fi
    
    # Remove lock file if it exists
    rm -f /tmp/audio_device.lock
    
    # Final cleanup of any remaining audio processes
    echo "Final audio cleanup..."
    fuser -k /dev/snd/* 2>/dev/null || true
    pulseaudio --kill 2>/dev/null || true
    
    echo "Cleanup completed"
    exit 0
}

trap 'echo "SIGINT received in shell script"; cleanup' SIGINT
trap 'echo "SIGTERM received in shell script"; cleanup' SIGTERM
trap 'echo "SIGQUIT received in shell script"; cleanup' SIGQUIT

# Clear any existing audio locks
rm -f /tmp/audio_device.lock
fuser -k /dev/snd/* 2>/dev/null || true
sleep 1

# Activate virtual environment and verify required modules
source .venv/bin/activate --system-site-packages

run_with_monitoring() {
    # Enable job control
    set -m
    
    setsid python3 main.py &
    PYTHON_PID=$!
    echo "Started Python process with PID: $PYTHON_PID (in new session)"

    # python3 main.py &
    # PYTHON_PID=$!
    # echo "Started Python process with PID: $PYTHON_PID"
    
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
required_modules = ['openai', 'pyaudio', 'numpy']
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
    echo "Starting AI Speaker System... (Shell PID: $$)"
    
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