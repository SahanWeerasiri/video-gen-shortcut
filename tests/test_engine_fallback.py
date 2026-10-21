import os
import sys
import asyncio
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

# Ensure src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from server import run_generation_task, tasks, tasks_lock, task_events


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
        mock_gen_instance.generate_text_to_video.assert_called_once()
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
            duration=2.0,
            width=704,
            height=512,
            seed=42,
            randomize_seed=True,
            guidance_scale=1.0,
            improve_texture=True,
            engine="selenium",
            loop=self.loop,
        )

        with tasks_lock:
            self.assertEqual(tasks[self.task_id]["status"], "completed")
            self.assertEqual(tasks[self.task_id].get("engine_used"), "selenium")

        mock_client.generate_text_to_video.assert_not_called()
        mock_selenium_cls.assert_called_once()
        mock_gen_instance.generate_text_to_video.assert_called_once()
        mock_gen_instance.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
