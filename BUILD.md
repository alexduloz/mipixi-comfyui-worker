# mipixi ComfyUI Worker - Build & Deploy

## Quick Start

### 1. Build
```bash
cd C:\Dev\runpod\serverless-worker
docker build -t mipixi/comfyui-worker:latest .
```
Takes ~10-15 min first time.

### 2. Push to Docker Hub
```bash
docker login
docker push mipixi/comfyui-worker:latest
```

### 3. Create Endpoint on RunPod
1. Go to https://www.runpod.io/console/serverless
2. **New Endpoint** > Custom
3. Settings:
   - **Name**: mipixi-comfyui
   - **Container Image**: `mipixi/comfyui-worker:latest`
   - **Container Disk**: 20 GB
   - **Network Volume**: Your volume (mounts at /runpod-volume)
   - **GPU**: RTX 4090 recommended
   - **Active Workers**: 0
   - **Max Workers**: 3
   - **Idle Timeout**: 5 seconds
   - **Execution Timeout**: 300 seconds

### 4. Test
```bash
curl -X POST "https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"workflow": {...}}}'
```

---

## Volume Structure

Your Network Volume must have:
```
/runpod-volume/
└── ComfyUI/
    ├── models/
    │   ├── checkpoints/
    │   ├── clip/         # qwen_2.5_vl_7b_fp8_scaled.safetensors, etc.
    │   ├── loras/
    │   ├── unet/         # flux1-krea-dev_fp8_scaled.safetensors, etc.
    │   ├── vae/          # ae.safetensors, etc.
    │   └── ...
    └── custom_nodes/     # (optional) auto-symlinked at startup
```

## What's Included

**Base image**: PyTorch 2.4 + CUDA 12.4

**Custom nodes baked in**:
- ComfyUI-Manager
- ComfyUI_IPAdapter_plus
- comfyui_controlnet_aux
- ComfyUI-VideoHelperSuite
- ComfyUI-KJNodes
- rgthree-comfy

**Additional custom nodes**: Place in `/runpod-volume/ComfyUI/custom_nodes/`, they'll be symlinked automatically.

## Updating

**New models**: Just add to volume, no rebuild needed.

**New custom nodes**: Add to volume, workers will pick them up on next cold start.

**Update worker image**:
```bash
docker build -t mipixi/comfyui-worker:latest .
docker push mipixi/comfyui-worker:latest
```
Then restart workers on RunPod console.
