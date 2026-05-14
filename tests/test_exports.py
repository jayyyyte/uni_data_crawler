from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.csv_io import read_csv, write_csv


class ExportTests(unittest.TestCase):
    def test_csv_exports_utf8_sig_and_preserve_multilingual_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            write_csv(path, [{"name": "東京大学", "local_name": "Eötvös Loránd Tudományegyetem"}], ["name", "local_name"])
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"\xef\xbb\xbf"))

            rows = read_csv(path)
            self.assertEqual(rows[0]["name"], "東京大学")
            self.assertEqual(rows[0]["local_name"], "Eötvös Loránd Tudományegyetem")


if __name__ == "__main__":
    unittest.main()

