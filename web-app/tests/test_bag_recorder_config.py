"""Reject ambiguous recorder settings before they can start a bag."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bag_recorder_config import load_recorder_config


class BagRecorderConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'bag_recorder_config.yml'

    def test_partial_config_merges_defaults_and_preserves_provenance(self):
        text = b'max_cache_size: 0\n'
        self.path.write_bytes(text)
        config = load_recorder_config(self.path)
        self.assertEqual(config['settings']['max_cache_size'], 0)
        self.assertEqual(config['settings']['storage'], 'mcap')
        self.assertEqual(config['settings']['compression_mode'], 'none')
        self.assertEqual(config['path'], str(self.path))
        self.assertEqual(config['sha256'], hashlib.sha256(text).hexdigest())

    def test_missing_malformed_and_non_mapping_files_are_errors(self):
        with self.assertRaisesRegex(ValueError, 'Cannot read'):
            load_recorder_config(self.path)
        for text in ('[broken', '', '- sqlite3\n', '1: value\n'):
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ValueError):
                    load_recorder_config(self.path)

    def test_rejects_typographical_errors_and_wrong_types(self):
        for text in ('max_cache_szie: 10', 'storage: null', 'serialization_format: 1',
                     'storage: "--all"', 'max_cache_size: true', 'max_cache_size: 1.5',
                     'max_cache_size: -1', 'max_cache_size: "100 MiB"',
                     'compression_queue_size: -1', 'compression_threads: false',
                     'max_cache_size: 18446744073709551616'):
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ValueError):
                    load_recorder_config(self.path)

    def test_rejects_invalid_compression_combinations(self):
        for text in ('compression_mode: yes', 'compression_mode: gzip',
                     'compression_mode: file\ncompression_format: ""',
                     'storage: mcap\ncompression_mode: message'):
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ValueError):
                    load_recorder_config(self.path)


if __name__ == '__main__':
    unittest.main()
