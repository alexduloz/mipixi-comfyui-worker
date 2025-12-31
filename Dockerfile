# mipixi ComfyUI Serverless Worker
# Models + custom nodes from Network Volume at /runpod-volume

FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# System dependencies
RUN apt-get update && apt-get install -y \
    git wget curl \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# ComfyUI (latest)
WORKDIR /workspace
RUN git clone https://github.com/comfyanonymous/ComfyUI.git

WORKDIR /workspace/ComfyUI
RUN pip install --no-cache-dir -r requirements.txt

# RunPod SDK
RUN pip install --no-cache-dir runpod requests

# Handler files
COPY handler.py /workspace/handler.py
COPY start.sh /workspace/start.sh
RUN chmod +x /workspace/start.sh

# Network Volume paths
RUN cat > /workspace/ComfyUI/extra_model_paths.yaml << 'EOF'
runpod_volume:
    base_path: /runpod-volume/ComfyUI/
    checkpoints: models/checkpoints/
    clip: models/clip/
    clip_vision: models/clip_vision/
    controlnet: models/controlnet/
    diffusion_models: models/diffusion_models/
    embeddings: models/embeddings/
    ipadapter: models/ipadapter/
    loras: models/loras/
    style_models: models/style_models/
    unet: models/unet/
    upscale_models: models/upscale_models/
    vae: models/vae/
EOF

WORKDIR /workspace
CMD ["/workspace/start.sh"]
