import tempfile
import unittest
from datetime import date
from pathlib import Path

from detection.reporting.retention import prune_daily_alerts, prune_evidence


class RetentionTests(unittest.TestCase):
    def test_prune_evidence_removes_old_date_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / '2020-01-01'
            recent = root / '2020-02-10'
            invalid = root / 'not-a-date'
            for folder in (old, recent, invalid):
                folder.mkdir()
                (folder / 'alert.jsonl').write_text('{}\n')
            removed = prune_evidence(root, 30, today=date(2020, 2, 15))
            self.assertEqual([path.name for path in removed], ['2020-01-01'])
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(invalid.exists())

    def test_zero_retention_disables_pruning(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / '2020-01-01'
            folder.mkdir()
            self.assertEqual(prune_evidence(directory, 0), [])
            self.assertTrue(folder.exists())

    def test_prune_daily_alerts_removes_old_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / '2020-01-01.jsonl'
            recent = root / '2020-02-10.jsonl'
            other = root / 'notes.txt'
            old.write_text('{}\n')
            recent.write_text('{}\n')
            other.write_text('keep')
            removed = prune_daily_alerts(root, 30, today=date(2020, 2, 15))
            self.assertEqual([path.name for path in removed], ['2020-01-01.jsonl'])
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(other.exists())


if __name__ == '__main__':
    unittest.main()
