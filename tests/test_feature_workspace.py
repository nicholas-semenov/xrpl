"""Check that future feature output paths cannot point to supplied data."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from feature_workspace import paths


class WorkspacePathTests(unittest.TestCase):
    def test_normal_output_and_source_separation(self):
        result = paths.output_path("train_features.parquet")
        self.assertEqual(result, paths.GENERATED.resolve() / "train_features.parquet")
        self.assertFalse(result.is_relative_to(paths.TRAIN_INPUT.resolve()))

    def test_rejects_absolute_paths_parent_escape_and_directory(self):
        for value in [paths.TRAIN_INPUT / "transactions.parquet", "../../data/traning_data/train/labels.csv", "."]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                paths.output_path(value)

    def test_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            generated = workspace / "generated"
            generated.mkdir()
            (generated / "source").symlink_to(paths.TRAIN_INPUT, target_is_directory=True)
            with patch.object(paths, "WORKSPACE", workspace), patch.object(paths, "GENERATED", generated):
                with self.assertRaises(ValueError):
                    paths.output_path("source/labels.csv")
            with patch.object(paths, "GENERATED", generated / "source"):
                with self.assertRaises(ValueError):
                    paths.output_path("labels.csv")


if __name__ == "__main__":
    unittest.main()
