from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.csv_io import write_csv
from glowbal_ingestion.manifest import write_run_manifest


class ManifestTests(unittest.TestCase):
    def test_manifest_counts_rows_without_changing_csv_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            csv_path = out_dir / "profiles.csv"
            write_csv(csv_path, [{"university_id": "demo"}], ["university_id"])

            manifest = write_run_manifest(
                out_dir,
                "pilot50_test",
                {"seed": "data/seed_universities_50.csv"},
                {"product_profiles": str(csv_path)},
            )

            loaded = json.loads((out_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["row_counts"]["product_profiles"], 1)
            self.assertEqual(loaded["run_id"], "pilot50_test")
            self.assertEqual(csv_path.read_text(encoding="utf-8-sig").splitlines()[0], "university_id")


if __name__ == "__main__":
    unittest.main()
