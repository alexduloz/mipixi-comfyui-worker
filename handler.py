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


def setup_volume_symlinks():
    """Symlink custom_nodes from Network Volume"""
    volume_nodes = "/runpod-volume/ComfyUI/custom_nodes"
    local_nodes = "/workspace/ComfyUI/custom_nodes"

    if not os.path.exists(volume_nodes):
        log("No custom_nodes on volume")
        return

    for node in os.listdir(volume_nodes):
        src = os.path.join(volume_nodes, node)
        dst = os.path.join(local_nodes, node)
        if os.path.isdir(src) and not os.path.exists(dst):
            try:
                os.symlink(src, dst)
                log(f"Linked: {node}")
            except Exception as e:
                log(f"Failed to link {node}: {e}")


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
        if i % 30 == 0:
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
    Output: {"images": [{"filename": "...", "data": "base64..."}], "prompt_id": "..."}
    """
    job_input = job.get("input", {})
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
setup_volume_symlinks()

if not start_comfyui():
    log("WARNING: ComfyUI may not be available")

runpod.serverless.start({"handler": handler})
