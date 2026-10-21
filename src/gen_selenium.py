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

    def switch_to_gradio_frame(self, max_wait: float = 15.0) -> bool:
        """
        Robustly navigates from default content into the nested Gradio generation iframe:
        top -> #outputIframeEl -> #genFrame.
        Handles dynamic iframe recreation and retries with backoff.
        """
        start = time.time()
        while time.time() - start < max_wait:
            try:
                self.driver.switch_to.default_content()

                # 1. Outer Perchance iframe
                outers = self.driver.find_elements("id", "outputIframeEl")
                if not outers:
                    outers = self.driver.find_elements("css selector", "iframe#outputIframeEl, iframe[src*='perchance']")
                if not outers:
                    time.sleep(0.4)
                    continue
                self.driver.switch_to.frame(outers[0])

                # 2. Inner Gradio iframe
                gens = self.driver.find_elements("id", "genFrame")
                if not gens:
                    gens = self.driver.find_elements("css selector", "iframe#genFrame, iframe[src*='hf.space']")
                if not gens:
                    time.sleep(0.4)
                    continue
                self.driver.switch_to.frame(gens[0])
                return True
            except Exception:
                time.sleep(0.4)

        raise TimeoutError(f"Could not switch to nested Gradio iframe within {max_wait}s.")

    def _find_element(self, candidates: list, timeout: float = 15.0, allow_hidden: bool = False):
        """
        Locates an element using a prioritized list of strategies:
        (by, selector). If not found, periodically re-synchronizes the nested iframe
        context to guard against frame detachment or dynamic re-renders.
        Supports hidden elements (e.g. Gradio input[type='file']).
        """
        start = time.time()
        last_switch = time.time()

        while time.time() - start < timeout:
            for by, selector in candidates:
                try:
                    elems = self.driver.find_elements(by, selector)
                    for el in elems:
                        # Gradio file inputs are hidden under visual dropzone wrappers
                        is_file = (by in ("xpath", "css selector") and "file" in selector) or (el.get_attribute("type") == "file")
                        if allow_hidden or is_file or el.is_displayed():
                            return el
                except Exception:
                    continue

            # Periodically re-ensure we are attached to the inner Gradio iframe
            if time.time() - last_switch >= 2.0:
                try:
                    self.switch_to_gradio_frame(max_wait=3.0)
                except Exception:
                    pass
                last_switch = time.time()

            time.sleep(0.3)

        # JavaScript fallback within the current frame context
        for by, selector in candidates:
            if allow_hidden or "file" in selector:
                try:
                    inp = self.driver.execute_script("return document.querySelector('input[type=\"file\"]');")
                    if inp:
                        return inp
                except Exception:
                    pass
            elif "Generate" in selector or "component-10" in selector or "component-17" in selector:
                try:
                    btn = self.driver.execute_script(
                        "return Array.from(document.querySelectorAll('button')).find("
                        "  b => b.textContent && b.textContent.includes('Generate') && b.offsetParent !== null"
                        ");"
                    )
                    if btn:
                        return btn
                except Exception:
                    pass

        tried = ", ".join(f"[{b}: '{s}']" for b, s in candidates)
        raise RuntimeError(f"Unable to locate element after {timeout:.1f}s across strategies: {tried}")

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
            tab_btn = self._find_element([
                ("id", "component-6-button"),
                ("xpath", "//*[@id='component-6-button']"),
                ("xpath", "//button[contains(normalize-space(.), 'image-to-video')]"),
                ("css selector", "button[id*='component-6']"),
            ], timeout=5.0)
            tab_btn.click()
            time.sleep(1)
        except Exception:
            pass

        # Ensure we remain in the Gradio frame before uploading
        self.switch_to_gradio_frame()

        # 2. Upload Image via file input (allow hidden file inputs)
        print(f"[*] Uploading image: {image_path}")
        if progress_callback:
            progress_callback("progress", {"message": "Uploading image to Perchance...", "percent": 25})
        file_input = self._find_element([
            ("xpath", "//input[@type='file']"),
            ("css selector", "input[type='file']"),
            ("xpath", "//input[@data-testid='file-upload']"),
        ], timeout=15.0, allow_hidden=True)
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

        # 4. Click Generate button using Multi-Strategy (Full XPath, ID, Normalized Text, JS)
        print("[*] Clicking 'Generate Image-to-Video' button...")
        if progress_callback:
            progress_callback("progress", {"message": "Submitted to Perchance GPU. Rendering video...", "percent": 35})
        gen_btn = self._find_element([
            ("id", "component-10"),
            ("xpath", "//*[@id='component-10']"),
            ("xpath", "/html/body/div/div/main/div/div/div/div[4]/div/div/div[2]/div/button"),
            ("xpath", "//button[contains(normalize-space(.), 'Generate Image-to-Video')]"),
            ("xpath", "//button[contains(@class, 'primary') and contains(normalize-space(.), 'Generate')]"),
            ("css selector", "button#component-10"),
            ("css selector", "button.primary.lg"),
        ], timeout=15.0)
        
        try:
            gen_btn.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", gen_btn)
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
            tab_btn = self._find_element([
                ("id", "component-13-button"),
                ("xpath", "//*[@id='component-13-button']"),
                ("xpath", "//button[contains(normalize-space(.), 'text-to-video')]"),
                ("css selector", "button[id*='component-13']"),
            ], timeout=5.0)
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

        # 3. Click Generate button using Multi-Strategy (Full XPath, ID, Normalized Text, JS)
        print("[*] Clicking 'Generate Text-to-Video' button...")
        if progress_callback:
            progress_callback("progress", {"message": "Submitted to Perchance GPU. Rendering video...", "percent": 35})
        gen_btn = self._find_element([
            ("id", "component-17"),
            ("xpath", "//*[@id='component-17']"),
            ("xpath", "/html/body/div/div/main/div/div/div/div[5]/div/div/div[2]/div/button"),
            ("xpath", "//button[contains(normalize-space(.), 'Generate Text-to-Video')]"),
            ("xpath", "//button[contains(@class, 'primary') and contains(normalize-space(.), 'Generate')]"),
            ("css selector", "button#component-17"),
            ("css selector", "button.primary.lg"),
        ], timeout=15.0)

        try:
            gen_btn.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", gen_btn)
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

            # 1. Immediately fail fast if Gradio / ZeroGPU error modal or toast appears
            toasts = self.driver.find_elements(
                "css selector",
                ".toast-wrap, [class*='toast'], .error, [class*='error']"
            )
            for t in toasts:
                try:
                    txt = t.text.strip()
                    if txt and any(term in txt.lower() for term in ("zerogpu", "quota exceeded", "exceeded", "error", "traceback")):
                        cleaned = txt.replace("×", "").replace("\n", " ").strip()
                        raise RuntimeError(f"Perchance/Gradio error on server: {cleaned}")
                except Exception as e:
                    if "Perchance/Gradio error on server" in str(e):
                        raise

            # 2. Check for video element with MP4 or blob stream
            videos = self.driver.find_elements("tag name", "video")
            for v in videos:
                src = v.get_attribute("src") or v.get_attribute("currentSrc")
                if not src:
                    # Check child <source> elements
                    for s in v.find_elements("tag name", "source"):
                        s_src = s.get_attribute("src")
                        if s_src:
                            src = s_src
                            break
                if src and any(ext in src for ext in (".mp4", "blob:", "/gradio_api/file=")):
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
