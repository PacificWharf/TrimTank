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
    upscale_training_outputs,
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
        Image = self._pillow_image()

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
            with Image.open(project_path / "training" / "001.png") as image:
                self.assertEqual(image.size, (1024, 1024))
            self.assertEqual(
                (project_path / "training" / "001.txt").read_text(encoding="utf-8").strip(),
                "sample_token",
            )
            config = (project_path / "training" / "kohya_dataset.toml").read_text(encoding="utf-8")
            self.assertIn("bucket_no_upscale = false", config)
            self.assertIn('resize_interpolation = "lanczos"', config)
            self.assertIn("random_crop = false", config)
            manifest = json.loads((project_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
            prepared = manifest["training"]["source.png"]["prepared"]
            self.assertEqual(prepared["width"], 1024)
            self.assertEqual(prepared["height"], 1024)

    def test_prepare_training_writes_exact_non_square_bucket(self):
        Image = self._pillow_image()

        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "dataset"
            self._prepare_sample_project(project_path, Image, (80, 64), (40, 32))

            with Image.open(project_path / "training" / "001.png") as image:
                self.assertEqual(image.size, (1152, 896))

    def test_upscale_training_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "dataset"
            create_project(str(project_path))

            with self.assertRaises(ValueError):
                upscale_training_outputs(str(project_path))

    def test_upscale_training_enlarges_small_prepared_pngs(self):
        Image = self._pillow_image()

        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "dataset"
            self._create_legacy_prepared_project(project_path, Image, (32, 32))
            caption_path = project_path / "training" / "001.txt"
            config_path = project_path / "training" / "kohya_dataset.toml"
            caption_before = caption_path.read_text(encoding="utf-8")
            config_before = config_path.read_text(encoding="utf-8")

            result = upscale_training_outputs(str(project_path), confirm_overwrite=True)

            self.assertEqual(result["changed_count"], 1)
            self.assertEqual(result["skipped_count"], 0)
            with Image.open(project_path / "training" / "001.png") as image:
                self.assertEqual(image.size, (1024, 1024))
            self.assertEqual(caption_path.read_text(encoding="utf-8"), caption_before)
            self.assertEqual(config_path.read_text(encoding="utf-8"), config_before)

    def test_upscale_training_skips_images_that_already_fit_bucket(self):
        Image = self._pillow_image()

        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "dataset"
            self._create_legacy_prepared_project(project_path, Image, (1024, 1024))

            result = upscale_training_outputs(str(project_path), confirm_overwrite=True)

            self.assertEqual(result["changed_count"], 0)
            self.assertEqual(result["skipped_count"], 1)
            with Image.open(project_path / "training" / "001.png") as image:
                self.assertEqual(image.size, (1024, 1024))

    def test_upscale_training_normalizes_off_by_one_prepared_pngs(self):
        Image = self._pillow_image()

        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "dataset"
            self._create_legacy_prepared_project(project_path, Image, (1023, 1024))

            result = upscale_training_outputs(str(project_path), confirm_overwrite=True)

            self.assertEqual(result["changed_count"], 1)
            with Image.open(project_path / "training" / "001.png") as image:
                self.assertEqual(image.size, (1024, 1024))

    def test_upscale_training_normalizes_non_square_prepared_pngs(self):
        Image = self._pillow_image()

        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "dataset"
            self._create_legacy_prepared_project(project_path, Image, (40, 32))

            result = upscale_training_outputs(str(project_path), confirm_overwrite=True)

            self.assertEqual(result["changed_count"], 1)
            with Image.open(project_path / "training" / "001.png") as image:
                self.assertEqual(image.size, (1152, 896))

    def _prepare_sample_project(
        self,
        project_path: Path,
        Image,
        source_size: tuple[int, int],
        crop_size: tuple[int, int],
    ) -> None:
        create_project(str(project_path))
        source_path = project_path / "inputs" / "source.png"
        Image.new("RGB", source_size, color=(255, 0, 0)).save(source_path)
        self._write_training_record(
            project_path,
            "source.png",
            {
                "status": "keep",
                "crop": {"x": 0, "y": 0, "width": crop_size[0], "height": crop_size[1]},
            },
        )
        update_project_settings(str(project_path), {"trigger_token": "sample_token"})
        prepare_training(str(project_path), confirm_clear_training=True)

    def _create_legacy_prepared_project(
        self,
        project_path: Path,
        Image,
        image_size: tuple[int, int],
    ) -> None:
        create_project(str(project_path))
        update_project_settings(str(project_path), {"trigger_token": "sample_token"})
        source_path = project_path / "inputs" / "source.png"
        Image.new("RGB", image_size, color=(255, 0, 0)).save(source_path)
        training_path = project_path / "training"
        Image.new("RGB", image_size, color=(255, 0, 0)).save(training_path / "001.png")
        (training_path / "001.txt").write_text("sample_token\n", encoding="utf-8")
        (training_path / "kohya_dataset.toml").write_text("existing config\n", encoding="utf-8")
        self._write_training_record(
            project_path,
            "source.png",
            {
                "status": "keep",
                "prepared": {
                    "image": "001.png",
                    "caption": "001.txt",
                    "source": "source.png",
                    "width": image_size[0],
                    "height": image_size[1],
                    "uses_crop": True,
                },
            },
        )

    def _pillow_image(self):
        try:
            from PIL import Image
        except ImportError as exc:
            raise unittest.SkipTest("Pillow is not installed") from exc

        return Image

    def _write_training_record(self, project_path: Path, filename: str, record: dict):
        manifest_path = project_path / MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["training"][filename] = record
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
