import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from scripts.history_store import HistoryStore


class HistoryRaceTests(unittest.TestCase):
    def test_racing_history_writer_cannot_overwrite_successful_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);remote=base/'remote.git'
            subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
            first=base/'first';first.mkdir();a=HistoryStore(first,remote=str(remote));a.load()
            (first/'state').mkdir();(first/'state/test.json').write_text('{"value":1}',encoding='utf-8')
            a.publish('initial')
            second=base/'second';second.mkdir();b=HistoryStore(second,remote=str(remote));b.load()
            (first/'state/test.json').write_text('{"value":2}',encoding='utf-8');a.publish('winner')
            (second/'state/test.json').write_text('{"value":3}',encoding='utf-8')
            with self.assertRaises(subprocess.CalledProcessError):b.publish('loser')
            third=base/'third';third.mkdir();c=HistoryStore(third,remote=str(remote));c.load()
            self.assertEqual(json.loads((third/'state/test.json').read_text(encoding='utf-8'))['value'],2)
