"""
mipixi ComfyUI Serverless Handler
Receives workflow JSON, executes on ComfyUI, returns images as base64
"""

import runpod
import requests
import time
import base64
import os
import subprocess
import sys

COMFY_URL = "http://127.0.0.1:8188"
comfy_process = None


def log(msg):
    print(f"[mipixi] {msg}", flush=True)


def find_volume_path():
    """Find where the network volume is mounted and where models are"""
    # Check various possible paths for models
    candidates = [
        ("/runpod-volume", "models"),           # Volume IS ComfyUI folder
        ("/runpod-volume/ComfyUI", "models"),   # Volume contains ComfyUI
        ("/workspace", "models"),                # Pod-style direct
        ("/workspace/ComfyUI", "models"),        # Pod-style nested
    ]

    log("Searching for models...")

    for base, models_subdir in candidates:
        models_path = os.path.join(base, models_subdir)
        log(f"Checking: {models_path}")

        if os.path.exists(models_path) and os.path.isdir(models_path):
            # Verify it has model subdirs
            subdirs = os.listdir(models_path)
            if any(d in subdirs for d in ['unet', 'checkpoints', 'clip', 'vae']):
                log(f"FOUND models at: {models_path}")
                for subdir in subdirs[:8]:
                    subpath = os.path.join(models_path, subdir)
                    if os.path.isdir(subpath):
                        files = os.listdir(subpath)[:3]
                        log(f"  {subdir}/: {files if files else '(empty)'}")
                return base

    # Debug: show what exists
    log("WARNING: No models found!")
    for path in ["/runpod-volume", "/workspace"]:
        if os.path.exists(path):
            contents = os.listdir(path)[:15]
            log(f"{path} contents: {contents}")
            # Go deeper
            for item in contents[:5]:
                subpath = os.path.join(path, item)
                if os.path.isdir(subpath):
                    subcontents = os.listdir(subpath)[:5]
                    log(f"  {item}/: {subcontents}")
        else:
            log(f"{path}: does not exist")

    return None


def setup_volume_symlinks(volume_path):
    """Symlink custom_nodes from Network Volume"""
    if not volume_path:
        return

    # Check for custom_nodes
    for nodes_path in [
        os.path.join(volume_path, "custom_nodes"),
        os.path.join(volume_path, "ComfyUI", "custom_nodes"),
    ]:
        if os.path.exists(nodes_path):
            local_nodes = "/workspace/ComfyUI/custom_nodes"
            log(f"Linking custom_nodes from {nodes_path}")

            for node in os.listdir(nodes_path):
                src = os.path.join(nodes_path, node)
                dst = os.path.join(local_nodes, node)
                if os.path.isdir(src) and not os.path.exists(dst):
                    try:
                        os.symlink(src, dst)
                        log(f"  Linked: {node}")
                    except Exception as e:
                        log(f"  Failed {node}: {e}")
            return

    log("No custom_nodes found on volume")


def start_comfyui():
    """Start ComfyUI and wait until ready"""
    global comfy_process

    log("Starting ComfyUI...")
    comfy_process = subprocess.Popen(
        [sys.executable, "main.py", "--listen", "0.0.0.0", "--port", "8188", "--disable-auto-launch"],
        cwd="/workspace/ComfyUI",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )

    # Wait for ready (max 3 min for cold start)
    for i in range(180):
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
            if r.status_code == 200:
                log("ComfyUI ready!")
                return True
        except:
            pass
        time.sleep(1)
        if i % 30 == 0 and i > 0:
            log(f"Waiting for ComfyUI... {i}s")

    log("ComfyUI failed to start")
    return False


def queue_prompt(workflow):
    """Send workflow to ComfyUI"""
    r = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow})
    return r.json()


def wait_for_result(prompt_id, timeout=300):
    """Poll until workflow completes"""
    start = time.time()

    while time.time() - start < timeout:
        try:
            r = requests.get(f"{COMFY_URL}/history/{prompt_id}")
            history = r.json()

            if prompt_id in history:
                return history[prompt_id]
        except:
            pass
        time.sleep(0.5)

    return None


def get_image(filename, subfolder="", folder_type="output"):
    """Download image from ComfyUI"""
    r = requests.get(f"{COMFY_URL}/view", params={
        "filename": filename,
        "subfolder": subfolder,
        "type": folder_type
    })
    return r.content


def handler(job):
    """
    RunPod handler

    Input: {"workflow": {...}, "timeout": 300}
    Or: {"debug": true} to get volume info
    Output: {"images": [{"filename": "...", "data": "base64..."}], "prompt_id": "..."}
    """
    job_input = job.get("input", {})

    # Debug mode - return volume info
    if job_input.get("debug"):
        info = {"paths": {}}
        for path in ["/runpod-volume", "/workspace", "/runpod-volume/models", "/workspace/models"]:
            if os.path.exists(path):
                try:
                    contents = os.listdir(path)[:20]
                    info["paths"][path] = contents
                except Exception as e:
                    info["paths"][path] = f"error: {e}"
            else:
                info["paths"][path] = "NOT EXISTS"

        # Check extra_model_paths.yaml
        yaml_path = "/workspace/ComfyUI/extra_model_paths.yaml"
        if os.path.exists(yaml_path):
            with open(yaml_path) as f:
                info["extra_model_paths"] = f.read()[:500]

        return info

    workflow = job_input.get("workflow")

    if not workflow:
        return {"error": "No workflow provided"}

    timeout = job_input.get("timeout", 300)

    # Queue workflow
    try:
        result = queue_prompt(workflow)
        prompt_id = result.get("prompt_id")

        if not prompt_id:
            error = result.get("error", result.get("node_errors", "Unknown error"))
            return {"error": "Queue failed", "details": error}

    except Exception as e:
        return {"error": f"Queue exception: {str(e)}"}

    log(f"Queued: {prompt_id}")

    # Wait for completion
    history = wait_for_result(prompt_id, timeout)

    if not history:
        return {"error": "Timeout", "prompt_id": prompt_id}

    # Check for execution errors
    if history.get("status", {}).get("status_str") == "error":
        return {"error": "Execution failed", "prompt_id": prompt_id}

    # Collect images
    images = []
    outputs = history.get("outputs", {})

    for node_id, node_out in outputs.items():
        if "images" not in node_out:
            continue

        for img in node_out["images"]:
            try:
                data = get_image(img["filename"], img.get("subfolder", ""))
                images.append({
                    "filename": img["filename"],
                    "node_id": node_id,
                    "data": base64.b64encode(data).decode()
                })
            except Exception as e:
                log(f"Failed to get image: {e}")

    log(f"Done: {len(images)} images")

    return {
        "images": images,
        "prompt_id": prompt_id
    }


# === Startup ===
log("=== mipixi ComfyUI Worker ===")
volume_path = find_volume_path()
setup_volume_symlinks(volume_path)

if not start_comfyui():
    log("WARNING: ComfyUI may not be available")

runpod.serverless.start({"handler": handler})
