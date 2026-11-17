import contextlib
import io
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from graftline._output import publish_bytes


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / 'input'
        self.source.write_bytes(b'ABC')
        self.output = self.directory / 'output'

    def run_cli(self, **options):
        return subprocess.run([sys.executable, '-I', '-S', str(ROOT / 'run.py'),
                               'run', str(ROOT / 'features/utf8proc'),
                               str(self.source), str(self.output), '--param', 'options=1070'],
                              capture_output=True, text=True, **options)

    def test_real_write_limit_leaves_no_final_file_and_same_path_retry_succeeds(self):
        def limit():
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE, (1, 1))
        result = self.run_cli(preexec_fn=limit)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.directory.glob('*.pending')))
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), b'abc')
        self.assertEqual(json.loads(result.stdout)['returnValue'], 3)

    def test_existing_file_and_dangling_symlink_are_not_replaced(self):
        self.output.write_bytes(b'foreign')
        self.output.chmod(0o640)
        before = self.output.stat()
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertEqual(self.output.read_bytes(), b'foreign')
        self.assertEqual(self.output.stat().st_mode, before.st_mode)
        self.output.unlink()
        self.output.symlink_to('missing-target')
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(os.readlink(self.output), 'missing-target')
        self.assertFalse(list(self.directory.glob('*.pending')))

    def test_modes_follow_original_run_umask_and_private_receipt_contract(self):
        self.assertEqual(self.run_cli(umask=0o027).returncode, 0)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o640)
        receipt = self.directory / 'receipt'
        publish_bytes(receipt, b'private')
        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)

    def test_cleanup_failure_reports_complete_publication_and_owned_leftover(self):
        message = io.StringIO()
        with patch('graftline._output.os.unlink', side_effect=PermissionError('held')), contextlib.redirect_stderr(message):
            publish_bytes(self.output, b'abc')
        self.assertEqual(self.output.read_bytes(), b'abc')
        stages = list(self.directory.glob('*.pending'))
        self.assertEqual(len(stages), 1)
        self.assertIn(str(stages[0]), message.getvalue())
        self.assertIn('Complete output published', message.getvalue())
        stages[0].unlink()

    def test_long_valid_destination_name_is_supported(self):
        self.output = self.directory / ('x' * 250)
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertEqual(self.output.read_bytes(), b'abc')


if __name__ == '__main__':
    unittest.main()
