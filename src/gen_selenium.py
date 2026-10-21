#!/usr/bin/env python3
"""
SeleniumBase Automation for LTX-Video on Perchance
Modeled after projects/headless-telebot/gen.py.
Interacts with https://perchance.org/ltx-video via UC (Undetected-Chromedriver) mode.
"""

import os
import sys
import time
import argparse
from typing import Optional, Dict, Any, Callable
import requests
from seleniumbase import Driver


class PerchanceLTXGenerator:
    """SeleniumBase-based browser generator for LTX-Video on Perchance."""

    def __init__(self, headless: Optional[bool] = None, binary_location: Optional[str] = None):
        self.url = "https://perchance.org/ltx-video"
        if headless is None:
            headless = os.getenv("SELENIUM_HEADLESS", "true").lower() in ("true", "1")
        if not binary_location:
            binary_location = os.getenv("BROWSER_BINARY_PATH", "/usr/bin/brave-browser")

        print(f"[*] Initializing SeleniumBase Driver (UC mode, headless={headless}, binary={binary_location})...")
        self.driver = Driver(
            uc=True,
            headless=headless,
            binary_location=binary_location,
        )
        self.init_page()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def init_page(self):
        """Opens Perchance and sets required localStorage/cookies."""
        print(f"[*] Navigating to {self.url}...")
        self.driver.uc_open_with_reconnect(self.url, 5)
        time.sleep(3)

        # Set localStorage similarly to headless-telebot
        try:
            self.driver.execute_script("window.localStorage.setItem('okayToShowNsfwUntil', '2066299973569');")
        except Exception:
            pass

        print("[+] Page loaded successfully: " + self.driver.title)

    def switch_to_gradio_frame(self):
        """Switches from top-level down into the nested Gradio generation iframe."""
        self.driver.switch_to.default_content()
        # 1. Outer Perchance iframe
        outer_iframe = self.driver.find_element("id", "outputIframeEl")
        self.driver.switch_to.frame(outer_iframe)
        # 2. Inner Gradio iframe
        gen_iframe = self.driver.find_element("id", "genFrame")
        self.driver.switch_to.frame(gen_iframe)

    def generate_image_to_video(
        self,
        image_path: str,
        prompt: str,
        output_path: str = "output.mp4",
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> str:
        """Uploads an image, inputs prompt, triggers generation, and downloads the video."""
        if not os.path.isabs(image_path):
            image_path = os.path.abspath(image_path)

        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Input image not found: {image_path}")

        if progress_callback:
            progress_callback("progress", {"message": "Switching to Image-to-Video tab in browser...", "percent": 20})

        self.switch_to_gradio_frame()
        time.sleep(1)

        # 1. Ensure 'image-to-video' tab is selected
        try:
            tab_btn = self.driver.find_element("xpath", "//button[contains(text(), 'image-to-video')]")
            tab_btn.click()
            time.sleep(1)
        except Exception:
            pass

        # 2. Upload Image via file input
        print(f"[*] Uploading image: {image_path}")
        if progress_callback:
            progress_callback("progress", {"message": "Uploading image to Perchance...", "percent": 25})
        file_input = self.driver.find_element("xpath", "//input[@type='file']")
        file_input.send_keys(image_path)
        print("[+] Image uploaded to UI. Waiting for thumbnail...")
        time.sleep(3)

        # 3. Enter Prompt
        print(f"[*] Entering prompt: {prompt}")
        if progress_callback:
            progress_callback("progress", {"message": "Entering animation prompt...", "percent": 30})
        textareas = self.driver.find_elements("tag name", "textarea")
        target_textarea = None
        for ta in textareas:
            if ta.is_displayed():
                target_textarea = ta
                break

        if not target_textarea and textareas:
            target_textarea = textareas[0]

        if target_textarea:
            target_textarea.clear()
            target_textarea.send_keys(prompt)

        # 4. Click Generate button
        print("[*] Clicking 'Generate Image-to-Video' button...")
        if progress_callback:
            progress_callback("progress", {"message": "Submitted to Perchance GPU. Rendering video...", "percent": 35})
        gen_btn = self.driver.find_element(
            "xpath", "//button[contains(text(), 'Generate Image-to-Video') or contains(text(), 'Generate')]"
        )
        gen_btn.click()
        print("[+] Generation started! Waiting for output video...")

        # 5. Poll for generated video element
        video_url = self._wait_for_video(progress_callback=progress_callback)
        print(f"[+] Found generated video URL: {video_url}")

        # 6. Download Video
        if progress_callback:
            progress_callback("progress", {"message": "Downloading finished MP4...", "percent": 95})
        self._download_video(video_url, output_path)
        print(f"[+] Video successfully saved to: {os.path.abspath(output_path)}")
        return output_path

    def generate_text_to_video(
        self,
        prompt: str,
        output_path: str = "output.mp4",
        negative_prompt: str = "",
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> str:
        """Inputs prompt, triggers text-to-video generation, and downloads the video."""
        if progress_callback:
            progress_callback("progress", {"message": "Switching to Text-to-Video tab in browser...", "percent": 20})

        self.switch_to_gradio_frame()
        time.sleep(1)

        # 1. Switch to 'text-to-video' tab
        try:
            tab_btn = self.driver.find_element("xpath", "//button[contains(text(), 'text-to-video')]")
            tab_btn.click()
            time.sleep(1)
        except Exception:
            pass

        # 2. Enter Prompt
        print(f"[*] Entering prompt: {prompt}")
        if progress_callback:
            progress_callback("progress", {"message": "Entering generation prompt...", "percent": 30})
        textareas = self.driver.find_elements("tag name", "textarea")
        target_textarea = None
        for ta in textareas:
            if ta.is_displayed():
                target_textarea = ta
                break

        if not target_textarea and textareas:
            target_textarea = textareas[0]

        if target_textarea:
            target_textarea.clear()
            target_textarea.send_keys(prompt)

        # 3. Click Generate button
        print("[*] Clicking 'Generate Text-to-Video' button...")
        if progress_callback:
            progress_callback("progress", {"message": "Submitted to Perchance GPU. Rendering video...", "percent": 35})
        gen_btn = self.driver.find_element(
            "xpath", "//button[contains(text(), 'Generate Text-to-Video') or contains(text(), 'Generate')]"
        )
        gen_btn.click()
        print("[+] Generation started! Waiting for output video...")

        # 4. Poll for generated video element
        video_url = self._wait_for_video(progress_callback=progress_callback)
        print(f"[+] Found generated video URL: {video_url}")

        # 5. Download Video
        if progress_callback:
            progress_callback("progress", {"message": "Downloading finished MP4...", "percent": 95})
        self._download_video(video_url, output_path)
        print(f"[+] Video successfully saved to: {os.path.abspath(output_path)}")
        return output_path

    def _wait_for_video(
        self,
        timeout: int = 180,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> str:
        """Polls for the video tag to be populated with an MP4 src."""
        start_time = time.time()
        last_report = 0
        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            if progress_callback and (elapsed - last_report >= 3.0):
                pct = min(35 + int((elapsed / timeout) * 55), 90)
                progress_callback(
                    "progress",
                    {"message": f"Browser rendering video... ({int(elapsed)}s elapsed)", "percent": pct},
                )
                last_report = elapsed

            self.switch_to_gradio_frame()
            videos = self.driver.find_elements("tag name", "video")
            for v in videos:
                src = v.get_attribute("src") or v.get_attribute("currentSrc")
                if src and ".mp4" in src:
                    return src
            time.sleep(2)
            sys.stdout.write(".")
            sys.stdout.flush()

        print()
        raise TimeoutError(f"Video generation timed out after {timeout} seconds.")

    def _download_video(self, url: str, output_path: str):
        """Downloads the video file to disk."""
        print(f"[*] Downloading video from {url}...")
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

    def close(self):
        """Quits the browser driver."""
        try:
            self.driver.quit()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="SeleniumBase automation for LTX-Video on Perchance.")
    parser.add_argument("-i", "--image", required=True, help="Path to input image.")
    parser.add_argument("-p", "--prompt", required=True, help="Animation prompt.")
    parser.add_argument(
        "-o",
        "--output",
        default=os.path.join(os.getenv("OUTPUT_DIR", "downloaded_files"), "output.mp4"),
        help="Output file path.",
    )
    parser.add_argument("--headed", action="store_true", help="Run browser in visible mode (default: headless).")

    args = parser.parse_args()

    gen = PerchanceLTXGenerator(headless=not args.headed)
    try:
        gen.generate_image_to_video(
            image_path=args.image,
            prompt=args.prompt,
            output_path=args.output,
        )
    finally:
        gen.close()


if __name__ == "__main__":
    main()
