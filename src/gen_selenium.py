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
import requests
from seleniumbase import Driver


class PerchanceLTXGenerator:
    """SeleniumBase-based browser generator for LTX-Video on Perchance."""

    def __init__(self, headless: bool = True):
        self.url = "https://perchance.org/ltx-video"
        print(f"[*] Initializing SeleniumBase Driver (UC mode, headless={headless})...")
        self.driver = Driver(
            uc=True,
            headless=headless,
            binary_location="/usr/bin/brave-browser",
        )
        self.init_page()

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

    def generate_image_to_video(self, image_path: str, prompt: str, output_path: str = "output.mp4") -> str:
        """Uploads an image, inputs prompt, triggers generation, and downloads the video."""
        if not os.path.isabs(image_path):
            image_path = os.path.abspath(image_path)

        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Input image not found: {image_path}")

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
        file_input = self.driver.find_element("xpath", "//input[@type='file']")
        file_input.send_keys(image_path)
        print("[+] Image uploaded to UI. Waiting for thumbnail...")
        time.sleep(3)

        # 3. Enter Prompt
        print(f"[*] Entering prompt: {prompt}")
        textareas = self.driver.find_elements("tag name", "textarea")
        # In Gradio, prompt textarea is typically the first visible one
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
        gen_btn = self.driver.find_element(
            "xpath", "//button[contains(text(), 'Generate Image-to-Video') or contains(text(), 'Generate')]"
        )
        gen_btn.click()
        print("[+] Generation started! Waiting for output video...")

        # 5. Poll for generated video element
        video_url = self._wait_for_video()
        print(f"[+] Found generated video URL: {video_url}")

        # 6. Download Video
        self._download_video(video_url, output_path)
        print(f"[+] Video successfully saved to: {os.path.abspath(output_path)}")
        return output_path

    def _wait_for_video(self, timeout: int = 180) -> str:
        """Polls for the video tag to be populated with an MP4 src."""
        start_time = time.time()
        while time.time() - start_time < timeout:
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
