#!/usr/bin/env python3
"""
FastAPI Server for LTX-Video Generation Web GUI
Provides REST endpoints and SSE streams for real-time video generation.
"""

import os
import sys
import uuid
import time
import asyncio
import threading
from typing import Optional, Dict, Any, List
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Load local environment if .env file exists
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                k = key.strip()
                v = val.strip().strip('"').strip("'")
                if k and (k not in os.environ or not os.environ[k]):
                    os.environ[k] = v

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ltx_video import LTXVideoClient, DEFAULT_BASE_URL, DEFAULT_NEGATIVE_PROMPT

# Configuration
GUI_HOST = os.getenv("GUI_HOST", "0.0.0.0")
GUI_PORT = int(os.getenv("GUI_PORT", "7860"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./downloaded_files")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="LTX-Video Studio", description="Web GUI for LTX-Video Generation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory task management
tasks_lock = threading.Lock()
tasks: Dict[str, Dict[str, Any]] = {}
task_events: Dict[str, asyncio.Queue] = {}

client = LTXVideoClient()


@app.get("/api/status")
def get_status():
    """Checks whether the Hugging Face Space is active."""
    try:
        is_online = client.check_and_wake_space(max_retries=1, retry_interval=1)
        return {"online": is_online, "backend": client.base_url, "status": "ready"}
    except Exception as e:
        return {"online": False, "backend": client.base_url, "status": "waking", "error": str(e)}


@app.get("/api/videos")
def list_videos():
    """Returns a list of previously generated videos from OUTPUT_DIR."""
    videos = []
    output_path = Path(OUTPUT_DIR)
    if output_path.exists():
        for f in sorted(output_path.glob("*.mp4"), key=os.path.getmtime, reverse=True):
            stat = f.stat()
            videos.append({
                "filename": f.name,
                "url": f"/downloaded_files/{f.name}",
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            })
    return {"videos": videos}


@app.delete("/api/videos/{filename}")
def delete_video(filename: str):
    """Deletes a video from OUTPUT_DIR."""
    # Prevent path traversal
    safe_name = os.path.basename(filename)
    target = Path(OUTPUT_DIR) / safe_name
    if target.exists() and target.is_file():
        target.unlink()
        return {"success": True, "message": f"Deleted {safe_name}"}
    raise HTTPException(status_code=404, detail="Video file not found")


def run_generation_task(
    task_id: str,
    prompt: str,
    negative_prompt: str,
    image_path: Optional[str],
    duration: float,
    width: Optional[int],
    height: Optional[int],
    seed: int,
    randomize_seed: bool,
    guidance_scale: float,
    improve_texture: bool,
    loop: asyncio.AbstractEventLoop,
):
    """Worker function executing generation in background thread."""
    queue = task_events.get(task_id)

    def progress_callback(msg: str, event_data: Dict[str, Any]):
        nonlocal loop, queue
        if not queue:
            return

        payload = {"type": msg, "data": event_data}
        if msg == "estimation":
            payload["rank"] = event_data.get("rank", 0)
            payload["queue_size"] = event_data.get("queue_size", 1)
            payload["eta"] = event_data.get("rank_eta", 0)
        elif msg == "progress":
            pdata = event_data.get("progress_data", [])
            if pdata:
                idx = pdata[0].get("index", 0)
                total = pdata[0].get("length", 1)
                payload["index"] = idx
                payload["total"] = total
                payload["percent"] = round((idx / max(total, 1)) * 100)

        # Thread-safe queue put
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(queue.put(payload), loop)

    timestamp = int(time.time())
    out_filename = f"ltx_{timestamp}_{task_id[:6]}.mp4"
    output_dest = os.path.join(OUTPUT_DIR, out_filename)

    try:
        if image_path and os.path.exists(image_path):
            result = client.generate_image_to_video(
                image_path=image_path,
                prompt=prompt,
                negative_prompt=negative_prompt,
                duration=duration,
                width=width,
                height=height,
                seed=seed,
                randomize_seed=randomize_seed,
                guidance_scale=guidance_scale,
                improve_texture=improve_texture,
                output_path=output_dest,
                progress_callback=progress_callback,
            )
        else:
            result = client.generate_text_to_video(
                prompt=prompt,
                negative_prompt=negative_prompt,
                duration=duration,
                width=width or 704,
                height=height or 512,
                seed=seed,
                randomize_seed=randomize_seed,
                guidance_scale=guidance_scale,
                improve_texture=improve_texture,
                output_path=output_dest,
                progress_callback=progress_callback,
            )

        with tasks_lock:
            tasks[task_id]["status"] = "completed"
            tasks[task_id]["video_url"] = f"/downloaded_files/{out_filename}"
            tasks[task_id]["filename"] = out_filename

        if queue and loop.is_running():
            completed_payload = {
                "type": "completed",
                "video_url": f"/downloaded_files/{out_filename}",
                "filename": out_filename,
            }
            asyncio.run_coroutine_threadsafe(queue.put(completed_payload), loop)

    except Exception as e:
        with tasks_lock:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["error"] = str(e)

        if queue and loop.is_running():
            error_payload = {"type": "error", "message": str(e)}
            asyncio.run_coroutine_threadsafe(queue.put(error_payload), loop)

    finally:
        # Cleanup uploaded temporary source image if needed
        if image_path and image_path.startswith("/tmp"):
            try:
                os.remove(image_path)
            except Exception:
                pass


@app.post("/api/generate")
async def start_generation(
    prompt: str = Form(...),
    negative_prompt: str = Form(DEFAULT_NEGATIVE_PROMPT),
    duration: float = Form(2.0),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
    guidance_scale: float = Form(1.0),
    improve_texture: bool = Form(True),
    seed: int = Form(42),
    randomize_seed: bool = Form(True),
    image: Optional[UploadFile] = File(None),
):
    """Initiates a generation job and returns a task_id."""
    task_id = str(uuid.uuid4())
    temp_image_path = None

    if image and image.filename:
        temp_dir = Path("/tmp/ltx_uploads")
        temp_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(image.filename).suffix or ".png"
        temp_image_path = str(temp_dir / f"{task_id}{ext}")
        with open(temp_image_path, "wb") as buffer:
            content = await image.read()
            buffer.write(content)

    queue = asyncio.Queue()
    task_events[task_id] = queue

    with tasks_lock:
        tasks[task_id] = {
            "id": task_id,
            "status": "queued",
            "prompt": prompt,
            "has_image": bool(temp_image_path),
            "created_at": time.time(),
        }

    loop = asyncio.get_running_loop()
    thread = threading.Thread(
        target=run_generation_task,
        args=(
            task_id,
            prompt,
            negative_prompt,
            temp_image_path,
            duration,
            width,
            height,
            seed,
            randomize_seed,
            guidance_scale,
            improve_texture,
            loop,
        ),
        daemon=True,
    )
    thread.start()

    return {"task_id": task_id, "status": "queued"}


@app.get("/api/progress/{task_id}")
async def stream_progress(task_id: str):
    """Server-Sent Events endpoint streaming progress for a specific task."""
    queue = task_events.get(task_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        yield f"data: {{\"type\": \"init\", \"task_id\": \"{task_id}\"}}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120)
                import json
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("completed", "error"):
                    break
            except asyncio.TimeoutError:
                yield "data: {\"type\": \"heartbeat\"}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Static files & Web UI
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

download_dir = Path(OUTPUT_DIR)
if download_dir.exists():
    app.mount("/downloaded_files", StaticFiles(directory=str(download_dir)), name="downloaded_files")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the main application UI."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>LTX-Video Studio GUI</h1><p>UI assets not found in src/static.</p>"


if __name__ == "__main__":
    print(f"[*] Starting LTX-Video Studio GUI on http://{GUI_HOST}:{GUI_PORT}")
    uvicorn.run("server:app", host=GUI_HOST, port=GUI_PORT, reload=False)
