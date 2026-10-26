"""Configuration reload and safe failure policy for MCAP postprocessing."""
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcap_postprocess import validate_config
from process_manager import ProcessManager


class PostprocessConfigurationTest(unittest.TestCase):
    def test_invalid_options_fail_before_starting_recording(self):
        for value in ({'enabled':'false'}, {'timeout_seconds':True},
                      {'timeout_seconds':0}, {'executable':'mcap'},
                      {'enabled':True,'executable':'/does/not/exist'}, {'level':3}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_config(value)

    def test_reload_applies_to_next_session_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.yml'
            path.write_text(yaml.safe_dump({'ros':{'mcap_postprocess':{'enabled':False}}}))
            manager = ProcessManager(Path(__file__).parents[1], {'_config_path':str(path)})
            first = manager.postprocess_settings()
            path.write_text(yaml.safe_dump({'ros':{'mcap_postprocess':{'enabled':True}}}))
            second = manager.postprocess_settings()
            self.assertFalse(first['enabled'])
            self.assertTrue(second['enabled'])
