#!/bin/bash
echo "=== mipixi ComfyUI Worker ==="

# Check volume
if [ -d "/runpod-volume/ComfyUI/models" ]; then
    echo "Volume OK: /runpod-volume/ComfyUI/models"
    echo "Models found:"
    ls /runpod-volume/ComfyUI/models/ 2>/dev/null | head -10
else
    echo "WARNING: No models at /runpod-volume/ComfyUI/models"
    ls -la /runpod-volume/ 2>/dev/null || echo "Volume not mounted"
fi

echo ""
echo "Starting handler..."
exec python /workspace/handler.py
