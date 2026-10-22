import os
import sys
import asyncio
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

# Ensure src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from server import app, run_generation_task, tasks, tasks_lock, task_events


class TestEngineFallback(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.task_id = "test-task-1234"
        self.queue = asyncio.Queue()
        task_events[self.task_id] = self.queue
        with tasks_lock:
            tasks[self.task_id] = {"id": self.task_id, "status": "queued"}

    def tearDown(self):
        self.loop.close()
        task_events.pop(self.task_id, None)
        with tasks_lock:
            tasks.pop(self.task_id, None)

    @patch("server.client")
    @patch("server.PerchanceLTXGenerator")
    def test_auto_engine_succeeds_without_fallback(self, mock_selenium_cls, mock_client):
        # Direct engine succeeds
        mock_client.generate_text_to_video.return_value = "http://example.com/video.mp4"
        
        run_generation_task(
            task_id=self.task_id,
            prompt="beautiful sunset",
            negative_prompt="blurry",
            image_path=None,
            duration=2.0,
            width=704,
            height=512,
            seed=42,
            randomize_seed=True,
            guidance_scale=1.0,
            improve_texture=True,
            engine="auto",
            loop=self.loop,
        )

        with tasks_lock:
            self.assertEqual(tasks[self.task_id]["status"], "completed")
        mock_client.generate_text_to_video.assert_called_once()
        mock_selenium_cls.assert_not_called()

    @patch("server.client")
    @patch("server.PerchanceLTXGenerator")
    def test_auto_engine_falls_back_to_selenium_on_direct_error(self, mock_selenium_cls, mock_client):
        # Direct engine fails (e.g. ZeroGPU quota)
        mock_client.generate_text_to_video.side_effect = RuntimeError("ZeroGPU quota exceeded")
        
        mock_gen_instance = MagicMock()
        mock_selenium_cls.return_value = mock_gen_instance
        mock_gen_instance.generate_text_to_video.return_value = "output.mp4"

        run_generation_task(
            task_id=self.task_id,
            prompt="cyberpunk city",
            negative_prompt="blurry",
            image_path=None,
            duration=2.0,
            width=704,
            height=512,
            seed=42,
            randomize_seed=True,
            guidance_scale=1.0,
            improve_texture=True,
            engine="auto",
            loop=self.loop,
        )

        with tasks_lock:
            self.assertEqual(tasks[self.task_id]["status"], "completed")
            self.assertEqual(tasks[self.task_id].get("engine_used"), "selenium_fallback")
        
        mock_client.generate_text_to_video.assert_called_once()
        mock_selenium_cls.assert_called_once()
        mock_gen_instance.generate_text_to_video.assert_called_once_with(
            prompt="cyberpunk city",
            negative_prompt="blurry",
            duration=2.0,
            width=704,
            height=512,
            seed=42,
            randomize_seed=True,
            guidance_scale=1.0,
            improve_texture=True,
            output_path=unittest.mock.ANY,
            progress_callback=unittest.mock.ANY,
        )
        mock_gen_instance.close.assert_called_once()

    @patch("server.client")
    @patch("server.PerchanceLTXGenerator")
    def test_direct_engine_does_not_fallback(self, mock_selenium_cls, mock_client):
        # Direct engine fails, but engine="direct" should not fall back
        mock_client.generate_text_to_video.side_effect = RuntimeError("ZeroGPU quota exceeded")

        run_generation_task(
            task_id=self.task_id,
            prompt="cyberpunk city",
            negative_prompt="blurry",
            image_path=None,
            duration=2.0,
            width=704,
            height=512,
            seed=42,
            randomize_seed=True,
            guidance_scale=1.0,
            improve_texture=True,
            engine="direct",
            loop=self.loop,
        )

        with tasks_lock:
            self.assertEqual(tasks[self.task_id]["status"], "error")
            self.assertIn("ZeroGPU quota exceeded", tasks[self.task_id]["error"])

        mock_client.generate_text_to_video.assert_called_once()
        mock_selenium_cls.assert_not_called()

    @patch("server.client")
    @patch("server.PerchanceLTXGenerator")
    def test_selenium_engine_runs_directly(self, mock_selenium_cls, mock_client):
        mock_gen_instance = MagicMock()
        mock_selenium_cls.return_value = mock_gen_instance
        mock_gen_instance.generate_text_to_video.return_value = "output.mp4"

        run_generation_task(
            task_id=self.task_id,
            prompt="futuristic car",
            negative_prompt="blurry",
            image_path=None,
            duration=8.0,
            width=704,
            height=512,
            seed=42,
            randomize_seed=True,
            guidance_scale=2.5,
            improve_texture=True,
            engine="selenium",
            loop=self.loop,
        )

        with tasks_lock:
            self.assertEqual(tasks[self.task_id]["status"], "completed")
            self.assertEqual(tasks[self.task_id].get("engine_used"), "selenium")

        mock_client.generate_text_to_video.assert_not_called()
        mock_selenium_cls.assert_called_once()
        mock_gen_instance.generate_text_to_video.assert_called_once_with(
            prompt="futuristic car",
            negative_prompt="blurry",
            duration=8.0,
            width=704,
            height=512,
            seed=42,
            randomize_seed=True,
            guidance_scale=2.5,
            improve_texture=True,
            output_path=unittest.mock.ANY,
            progress_callback=unittest.mock.ANY,
        )
        mock_gen_instance.close.assert_called_once()

    @patch("server.client")
    @patch("server.PerchanceLTXGenerator")
    @patch("os.path.exists", return_value=True)
    def test_selenium_engine_image_to_video_forwards_all_parameters(self, mock_exists, mock_selenium_cls, mock_client):
        mock_gen_instance = MagicMock()
        mock_selenium_cls.return_value = mock_gen_instance
        mock_gen_instance.generate_image_to_video.return_value = "output.mp4"

        run_generation_task(
            task_id=self.task_id,
            prompt="animate character",
            negative_prompt="distorted",
            image_path="/tmp/fake_image.png",
            duration=4.5,
            width=512,
            height=512,
            seed=100,
            randomize_seed=False,
            guidance_scale=3.0,
            improve_texture=False,
            engine="selenium",
            loop=self.loop,
        )

        with tasks_lock:
            self.assertEqual(tasks[self.task_id]["status"], "completed")
            self.assertEqual(tasks[self.task_id].get("engine_used"), "selenium")

        mock_client.generate_image_to_video.assert_not_called()
        mock_selenium_cls.assert_called_once()
        mock_gen_instance.generate_image_to_video.assert_called_once_with(
            image_path="/tmp/fake_image.png",
            prompt="animate character",
            negative_prompt="distorted",
            duration=4.5,
            width=512,
            height=512,
            seed=100,
            randomize_seed=False,
            guidance_scale=3.0,
            improve_texture=False,
            output_path=unittest.mock.ANY,
            progress_callback=unittest.mock.ANY,
        )
        mock_gen_instance.close.assert_called_once()

    def test_cors_configuration_is_secure(self):
        """Verifies that CORS middleware does not permit wildcard '*' origins."""
        cors_middlewares = [
            m for m in app.user_middleware
            if "CORSMiddleware" in str(m.cls)
        ]
        self.assertTrue(len(cors_middlewares) > 0, "CORSMiddleware should be installed on app")
        for middleware in cors_middlewares:
            allowed_origins = middleware.kwargs.get("allow_origins", [])
            self.assertNotIn("*", allowed_origins, "Wildcard '*' must not be allowed in CORS origins")
            self.assertTrue(len(allowed_origins) > 0, "Explicit allowed origins should be configured")

    @patch("gen_selenium.Driver")
    def test_perchance_generator_configures_parameters_via_js(self, mock_driver_cls):
        from gen_selenium import PerchanceLTXGenerator
        mock_driver = MagicMock()
        mock_driver_cls.return_value = mock_driver

        gen = PerchanceLTXGenerator(headless=True)
        gen._configure_parameters(
            duration=8.0,
            negative_prompt="blurry, distorted",
            width=704,
            height=384,
            seed=12345,
            randomize_seed=False,
            guidance_scale=1.5,
        )

        self.assertEqual(mock_driver.execute_script.call_count, 2)
        args, _ = mock_driver.execute_script.call_args_list[1]
        js_code = args[0]
        params = args[1]
        self.assertIn("component-27", js_code)
        self.assertIn("component-45", js_code)
        self.assertIn("component-44", js_code)
        self.assertIn("component-35", js_code)
        self.assertIn("component-37", js_code)
        self.assertIn("component-38", js_code)
        self.assertEqual(params["duration"], 8.0)
        self.assertEqual(params["width"], 704)
        self.assertEqual(params["height"], 384)
        self.assertEqual(params["seed"], 12345)
        self.assertFalse(params["randomize_seed"])
        self.assertEqual(params["negative_prompt"], "blurry, distorted")


if __name__ == "__main__":

    unittest.main()

