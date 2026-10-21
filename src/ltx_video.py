#!/usr/bin/env python3
"""
LTX-Video Automation Client
Direct Request/Response Automation for Lightricks LTX-Video Distilled
Reverse-engineered from Gradio 5 API and Perchance integration.
"""

import os
import sys
import json
import time
import string
import random
import mimetypes
import argparse
from typing import Optional, Dict, Any, Tuple
import requests

DEFAULT_BASE_URL = os.getenv("LTX_BACKEND_URL", "https://lightricks-ltx-video-distilled.hf.space")
DEFAULT_NEGATIVE_PROMPT = os.getenv(
    "DEFAULT_NEGATIVE_PROMPT", "worst quality, inconsistent motion, blurry, jittery, distorted"
)


class LTXVideoClient:
    """Client for generating AI videos using the LTX-Video Distilled Gradio API."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout or int(os.getenv("REQUEST_TIMEOUT", "180"))
        self.session = requests.Session()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        }
        hf_token = os.getenv("HF_TOKEN")
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
        self.session.headers.update(headers)

    def check_and_wake_space(self, max_retries: int = 6, retry_interval: int = 5) -> bool:
        """
        Verifies that the Hugging Face space is active. If the space is asleep,
        it pings /config to wake it up and waits until it responds with 200 OK.
        """
        config_url = f"{self.base_url}/config"
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.get(config_url, timeout=10)
                if resp.status_code == 200:
                    return True
                elif resp.status_code in (503, 504):
                    print(f"[*] Hugging Face Space is waking up (attempt {attempt}/{max_retries})...")
                else:
                    print(f"[!] Space returned HTTP {resp.status_code}, retrying...")
            except requests.exceptions.RequestException as e:
                print(f"[*] Connection attempt {attempt}/{max_retries} waiting for space: {e}")

            time.sleep(retry_interval)

        raise RuntimeError(
            f"Hugging Face space at {self.base_url} is unreachable or did not wake up after {max_retries * retry_interval}s."
        )

    @staticmethod
    def generate_session_hash(length: int = 11) -> str:
        """
        Generate a random session hash.
        This replicates Gradio's client-side hash generation:
        JavaScript: Math.random().toString(36).substring(2, 13)
        """
        alphabet = string.ascii_lowercase + string.digits
        return "".join(random.choices(alphabet, k=length))

    def upload_image(self, file_path: str) -> Dict[str, Any]:
        """
        Uploads an image file to the Gradio space's /upload endpoint.
        Returns the Gradio FileData dictionary.
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "image/png"

        upload_id = self.generate_session_hash(11)
        upload_url = f"{self.base_url}/gradio_api/upload?upload_id={upload_id}"

        print(f"[*] Uploading '{filename}' ({file_size / 1024:.1f} KB)...")
        with open(file_path, "rb") as f:
            files = {"files": (filename, f, mime_type)}
            resp = self.session.post(upload_url, files=files, timeout=60)

        if resp.status_code != 200:
            raise RuntimeError(f"Upload failed (status {resp.status_code}): {resp.text}")

        uploaded_paths = resp.json()
        if not uploaded_paths:
            raise RuntimeError("Upload returned empty path array.")

        server_path = uploaded_paths[0]
        file_data = {
            "path": server_path,
            "url": f"{self.base_url}/gradio_api/file={server_path}",
            "orig_name": filename,
            "size": file_size,
            "mime_type": mime_type,
            "meta": {"_type": "gradio.FileData"},
        }
        print(f"[+] Image uploaded successfully. Remote path: {server_path}")
        return file_data

    def calculate_optimal_dimensions(
        self, file_data: Dict[str, Any], default_w: int = 704, default_h: int = 512
    ) -> Tuple[int, int]:
        """
        Queries fn_index 0 on the Gradio space to determine optimal width and height
        preserving the aspect ratio of the input image (rounded to multiples of 32).
        """
        session_hash = self.generate_session_hash()
        payload = {
            "data": [file_data, default_h, default_w],
            "event_data": None,
            "fn_index": 0,
            "trigger_id": 8,
            "session_hash": session_hash,
        }

        join_url = f"{self.base_url}/gradio_api/queue/join?"
        resp = self.session.post(join_url, json=payload, timeout=15)
        if resp.status_code != 200:
            return default_w, default_h

        # Listen to SSE stream for resolution update
        sse_url = f"{self.base_url}/gradio_api/queue/data?session_hash={session_hash}"
        headers = {"Accept": "text/event-stream"}
        try:
            with self.session.get(sse_url, headers=headers, stream=True, timeout=15) as sse:
                for line in sse.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data:"):
                        event = json.loads(decoded[5:].strip())
                        if event.get("msg") == "process_completed":
                            data = event.get("output", {}).get("data", [])
                            if len(data) >= 2:
                                h = data[0].get("value", default_h)
                                w = data[1].get("value", default_w)
                                return int(w), int(h)
                            break
        except Exception:
            pass

        return default_w, default_h

    def generate_image_to_video(
        self,
        image_path: str,
        prompt: str,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        duration: float = 2.0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        seed: int = 42,
        randomize_seed: bool = True,
        guidance_scale: float = 1.0,
        improve_texture: bool = True,
        output_path: str = "output.mp4",
    ) -> str:
        """
        Runs the Image-to-Video generation pipeline.
        Uploads image, determines dimensions, enqueues task, monitors progress,
        and downloads the generated MP4 file.
        """
        # 0. Health check and wake space if sleeping
        self.check_and_wake_space()

        # 1. Upload Image
        file_data = self.upload_image(image_path)

        # 2. Dimensions
        if width is None or height is None:
            print("[*] Calculating optimal resolution from image aspect ratio...")
            calc_w, calc_h = self.calculate_optimal_dimensions(file_data)
            width = width or calc_w
            height = height or calc_h

        # Ensure divisible by 32
        width = (width // 32) * 32
        height = (height // 32) * 32
        print(f"[*] Target resolution: {width}x{height}, duration: {duration}s")

        # 3. Create Session Hash
        session_hash = self.generate_session_hash()

        # 4. Prepare Queue Join Payload (fn_index 5 = Image-to-Video)
        join_payload = {
            "data": [
                prompt,               # ID 9: Prompt
                negative_prompt,      # ID 35: Negative Prompt
                file_data,            # ID 8: Input Image
                None,                 # ID 7: video_i
                height,               # ID 44: Height (must be div by 32)
                width,                # ID 45: Width (must be div by 32)
                "image-to-video",     # ID 34: task
                duration,             # ID 27: Video Duration (seconds)
                9,                    # ID 22: Frames to use from input (N*8+1)
                seed,                 # ID 37: Seed
                randomize_seed,       # ID 38: Randomize Seed
                guidance_scale,       # ID 41: Guidance Scale (CFG)
                improve_texture,      # ID 28: Improve Texture (multi-scale)
            ],
            "event_data": None,
            "fn_index": 5,
            "trigger_id": 10,
            "session_hash": session_hash,
        }

        # 5. Join Queue
        print(f"[*] Submitting generation job (Session: {session_hash})...")
        join_url = f"{self.base_url}/gradio_api/queue/join?"
        join_resp = self.session.post(join_url, json=join_payload, timeout=20)
        if join_resp.status_code != 200:
            raise RuntimeError(f"Queue join failed ({join_resp.status_code}): {join_resp.text}")

        join_data = join_resp.json()
        event_id = join_data.get("event_id")
        print(f"[+] Enqueued successfully. Event ID: {event_id}")

        # 6. Stream SSE events & wait for completion
        video_url = self._wait_for_completion(session_hash, event_id)

        # 7. Download output video
        print(f"[*] Downloading generated video from {video_url}...")
        self._download_file(video_url, output_path)
        print(f"[+] Video successfully saved to: {os.path.abspath(output_path)}")
        return output_path

    def generate_text_to_video(
        self,
        prompt: str,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        duration: float = 2.0,
        width: int = 704,
        height: int = 512,
        seed: int = 42,
        randomize_seed: bool = True,
        guidance_scale: float = 1.0,
        improve_texture: bool = True,
        output_path: str = "output.mp4",
    ) -> str:
        """Runs the Text-to-Video generation pipeline (fn_index 4)."""
        self.check_and_wake_space()
        width = (width // 32) * 32
        height = (height // 32) * 32
        session_hash = self.generate_session_hash()

        join_payload = {
            "data": [
                prompt,
                negative_prompt,
                None,             # No input image
                None,             # No video input
                height,
                width,
                "text-to-video",
                duration,
                9,
                seed,
                randomize_seed,
                guidance_scale,
                improve_texture,
            ],
            "event_data": None,
            "fn_index": 4,
            "trigger_id": 17,
            "session_hash": session_hash,
        }

        print(f"[*] Submitting Text-to-Video job (Session: {session_hash})...")
        join_url = f"{self.base_url}/gradio_api/queue/join?"
        join_resp = self.session.post(join_url, json=join_payload, timeout=20)
        if join_resp.status_code != 200:
            raise RuntimeError(f"Queue join failed ({join_resp.status_code}): {join_resp.text}")

        event_id = join_resp.json().get("event_id")
        print(f"[+] Enqueued successfully. Event ID: {event_id}")

        video_url = self._wait_for_completion(session_hash, event_id)
        self._download_file(video_url, output_path)
        print(f"[+] Video saved to: {os.path.abspath(output_path)}")
        return output_path

    def _wait_for_completion(self, session_hash: str, event_id: str) -> str:
        """Listens to SSE stream until process_completed is received."""
        sse_url = f"{self.base_url}/gradio_api/queue/data?session_hash={session_hash}"
        headers = {"Accept": "text/event-stream"}

        start_time = time.time()
        with self.session.get(sse_url, headers=headers, stream=True, timeout=self.timeout) as resp:
            for line in resp.iter_lines():
                if time.time() - start_time > self.timeout:
                    raise TimeoutError(f"Job timed out after {self.timeout}s")

                if not line:
                    continue

                decoded = line.decode("utf-8")
                if not decoded.startswith("data:"):
                    continue

                raw_json = decoded[5:].strip()
                try:
                    event = json.loads(raw_json)
                except json.JSONDecodeError:
                    continue

                msg = event.get("msg")
                if msg == "estimation":
                    rank = event.get("rank", 0)
                    q_size = event.get("queue_size", 1)
                    eta = event.get("rank_eta", 0)
                    print(f"[*] Queue status: Position {rank+1}/{q_size} (ETA: {eta:.1f}s)")
                elif msg == "process_starts":
                    print("[*] Generation processing started...")
                elif msg == "progress":
                    progress_data = event.get("progress_data", [])
                    if progress_data:
                        unit = progress_data[0].get("unit", "steps")
                        index = progress_data[0].get("index", 0)
                        length = progress_data[0].get("length", 1)
                        print(f"[*] Generating: {index}/{length} {unit}")
                elif msg == "process_completed":
                    if not event.get("success", False):
                        raise RuntimeError(f"Generation failed on server: {event}")

                    out_data = event.get("output", {}).get("data", [])
                    if not out_data or "video" not in out_data[0]:
                        raise RuntimeError(f"No video found in output: {event}")

                    video_info = out_data[0]["video"]
                    video_url = video_info.get("url")
                    if not video_url and "path" in video_info:
                        video_url = f"{self.base_url}/gradio_api/file={video_info['path']}"

                    gen_duration = event.get("output", {}).get("duration", 0)
                    print(f"[+] Generation complete in {gen_duration:.2f}s!")
                    return video_url
                elif msg == "close_stream":
                    break

        raise RuntimeError("SSE stream closed before generation completed.")

    def _download_file(self, url: str, output_path: str):
        """Downloads a remote file with streaming chunks."""
        resp = self.session.get(url, stream=True, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to download video ({resp.status_code}): {resp.text}")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        sys.stdout.write(f"\rDownloading: {percent:.1f}% ({downloaded}/{total_size} bytes)")
                        sys.stdout.flush()

        print()


def main():
    parser = argparse.ArgumentParser(
        description="Automate AI video generation using LTX-Video Distilled (Lightricks)."
    )
    parser.add_argument("-i", "--image", type=str, help="Path to input image for Image-to-Video generation.")
    parser.add_argument("-p", "--prompt", type=str, required=True, help="Prompt describing the animation / scene.")
    parser.add_argument("-n", "--negative-prompt", type=str, default=DEFAULT_NEGATIVE_PROMPT, help="Negative prompt.")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=os.path.join(os.getenv("OUTPUT_DIR", "downloaded_files"), "output.mp4"),
        help="Output MP4 file path.",
    )
    parser.add_argument("-d", "--duration", type=float, default=2.0, help="Target video duration in seconds (0.3s - 8.5s).")
    parser.add_argument("-W", "--width", type=int, default=None, help="Video width (must be divisible by 32).")
    parser.add_argument("-H", "--height", type=int, default=None, help="Video height (must be divisible by 32).")
    parser.add_argument("-s", "--seed", type=int, default=42, help="Seed value.")
    parser.add_argument("--fixed-seed", action="store_true", help="Do not randomize seed.")
    parser.add_argument("--cfg", type=float, default=1.0, help="Guidance scale / CFG.")
    parser.add_argument("--no-improve-texture", action="store_true", help="Disable multi-scale texture enhancement (faster).")

    args = parser.parse_args()

    client = LTXVideoClient()

    if args.image:
        client.generate_image_to_video(
            image_path=args.image,
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            duration=args.duration,
            width=args.width,
            height=args.height,
            seed=args.seed,
            randomize_seed=not args.fixed_seed,
            guidance_scale=args.cfg,
            improve_texture=not args.no_improve_texture,
            output_path=args.output,
        )
    else:
        print("[*] No input image provided. Running Text-to-Video generation...")
        client.generate_text_to_video(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            duration=args.duration,
            width=args.width or 704,
            height=args.height or 512,
            seed=args.seed,
            randomize_seed=not args.fixed_seed,
            guidance_scale=args.cfg,
            improve_texture=not args.no_improve_texture,
            output_path=args.output,
        )


if __name__ == "__main__":
    main()
