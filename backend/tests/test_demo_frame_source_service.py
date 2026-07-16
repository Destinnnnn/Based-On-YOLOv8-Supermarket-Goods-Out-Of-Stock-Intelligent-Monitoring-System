import unittest
from pathlib import Path

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.demo_frame_source_service import DemoFrameSourceService


class DemoFrameSourceServiceTests(unittest.TestCase):
    def test_unknown_source_is_rejected(self):
        service = DemoFrameSourceService(project_root=PROJECT_ROOT)

        with self.assertRaises(ValueError):
            service.create_session(source="../outside")

    def test_uses_existing_test_dataset_and_repeats_frames_deterministically(self):
        service = DemoFrameSourceService(project_root=PROJECT_ROOT)

        first_session = service.create_session(
            source="test",
            max_images=6,
            seed=17,
            repeat_min=5,
            repeat_max=10,
            empty_interval=5,
            empty_frames=3,
        )
        second_session = service.create_session(
            source="test",
            max_images=6,
            seed=17,
            repeat_min=5,
            repeat_max=10,
            empty_interval=5,
            empty_frames=3,
        )

        first_names = [first_session.next_frame().image_name for _ in range(50)]
        second_names = [second_session.next_frame().image_name for _ in range(50)]

        self.assertEqual(first_session.image_count, 6)
        self.assertEqual(first_names, second_names)
        self.assertIn("__empty_frame__.jpg", first_names)

    def test_repeated_real_frames_share_cache_key(self):
        service = DemoFrameSourceService(project_root=PROJECT_ROOT)
        session = service.create_session(
            source="test",
            max_images=1,
            seed=1,
            repeat_min=3,
            repeat_max=3,
            empty_interval=0,
            empty_frames=0,
        )

        frames = [session.next_frame() for _ in range(3)]

        self.assertEqual({frame.kind for frame in frames}, {"image"})
        self.assertEqual(len({frame.cache_key for frame in frames}), 1)
        self.assertEqual(len({frame.image_name for frame in frames}), 1)

    def test_empty_frames_are_jpeg_data_urls_without_cache_key(self):
        service = DemoFrameSourceService(project_root=PROJECT_ROOT)
        session = service.create_session(
            source="test",
            max_images=1,
            seed=1,
            repeat_min=1,
            repeat_max=1,
            empty_interval=1,
            empty_frames=3,
        )

        self.assertEqual(session.next_frame().kind, "image")
        empty_frames = [session.next_frame() for _ in range(3)]

        self.assertTrue(all(frame.kind == "empty" for frame in empty_frames))
        self.assertTrue(all(frame.cache_key is None for frame in empty_frames))
        self.assertTrue(
            all(
                frame.image_data_url.startswith("data:image/jpeg;base64,")
                for frame in empty_frames
            )
        )


if __name__ == "__main__":
    unittest.main()
