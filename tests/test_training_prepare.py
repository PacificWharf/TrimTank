import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trimtank.projects import (
    MANIFEST_FILENAME,
    create_project,
    get_project_bucket_stats,
    prepare_training,
    update_project_settings,
)


class TrainingPrepareTests(unittest.TestCase):
    def test_bucket_stats_use_saved_crop_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "dataset"
            create_project(str(project_path))
            source_path = project_path / "inputs" / "source.png"
            source_path.write_bytes(b"not a real image")
            self._write_training_record(
                project_path,
                "source.png",
                {
                    "status": "keep",
                    "crop": {"x": 0, "y": 0, "width": 512, "height": 768},
                },
            )

            stats = get_project_bucket_stats(str(project_path))

            self.assertEqual(stats["total_images"], 1)
            self.assertEqual(stats["bucket_count"], 1)
            self.assertEqual(stats["buckets"][0]["count"], 1)

    def test_update_project_settings_normalizes_values(self):
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "dataset"
            create_project(str(project_path))

            result = update_project_settings(
                str(project_path),
                {
                    "trigger_token": "  sample_token  ",
                    "num_repeats": "12",
                    "enable_bucket": False,
                    "resolution": "512",
                    "min_bucket_reso": "256",
                    "max_bucket_reso": "1024",
                    "bucket_reso_steps": "64",
                },
            )

            self.assertEqual(result["settings"]["trigger_token"], "sample_token")
            self.assertEqual(result["settings"]["num_repeats"], 12)
            self.assertFalse(result["settings"]["enable_bucket"])
            self.assertEqual(result["settings"]["resolution"], 512)

    def test_prepare_training_writes_png_txt_and_config_when_pillow_available(self):
        try:
            from PIL import Image
        except ImportError as exc:
            raise unittest.SkipTest("Pillow is not installed") from exc

        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "dataset"
            create_project(str(project_path))
            source_path = project_path / "inputs" / "source.png"
            Image.new("RGB", (64, 64), color=(255, 0, 0)).save(source_path)
            self._write_training_record(
                project_path,
                "source.png",
                {
                    "status": "keep",
                    "crop": {"x": 8, "y": 8, "width": 32, "height": 32},
                },
            )
            update_project_settings(str(project_path), {"trigger_token": "sample_token"})

            result = prepare_training(str(project_path), confirm_clear_training=True)

            self.assertEqual(result["count"], 1)
            self.assertTrue((project_path / "training" / "001.png").exists())
            self.assertEqual(
                (project_path / "training" / "001.txt").read_text(encoding="utf-8").strip(),
                "sample_token",
            )
            self.assertTrue((project_path / "training" / "kohya_dataset.toml").exists())

    def _write_training_record(self, project_path: Path, filename: str, record: dict):
        manifest_path = project_path / MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["training"][filename] = record
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
