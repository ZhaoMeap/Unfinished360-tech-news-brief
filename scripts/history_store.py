"""Same-repo append-only history checkout with fast-forward-only publication."""
import shutil
import subprocess
from pathlib import Path

BRANCH='brief-history'


class HistoryStore:
    def __init__(self,root,checkout=None,remote=None):
        self.root=Path(root)
        self.checkout=Path(checkout or self.root/'.history')
        self.remote=remote or self.git(self.root,'remote','get-url','origin').strip()

    @staticmethod
    def git(cwd,*args):
        result=subprocess.run(['git','-C',str(cwd),*args],capture_output=True,text=True,check=True,timeout=90)
        return result.stdout

    def load(self):
        if self.checkout.exists():
            raise ValueError('history checkout already exists; do not overwrite it')
        probe=subprocess.run(['git','ls-remote','--exit-code','--heads',self.remote,BRANCH],capture_output=True,text=True,timeout=60)
        if probe.returncode not in (0,2):
            raise RuntimeError('history remote unavailable')
        self.checkout.mkdir(parents=True)
        self.git(self.checkout,'init','-b',BRANCH)
        self.git(self.checkout,'remote','add','origin',self.remote)
        self.git(self.checkout,'config','user.name','github-actions[bot]')
        self.git(self.checkout,'config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
        if probe.returncode==0:
            self.git(self.checkout,'fetch','--depth=1','origin',BRANCH)
            self.git(self.checkout,'reset','--hard','FETCH_HEAD')
        self.restore()
        return probe.returncode==0

    def restore(self):
        for pattern in ('state/*.json','reports/daily/*.md','data/daily/*.json'):
            for source in self.checkout.glob(pattern):
                target=self.root/source.relative_to(self.checkout)
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(source.read_bytes())

    def publish(self,message):
        # Only a strict allowlist of pipeline outputs is copied, never .env or credentials.
        for pattern in ('state/*.json','reports/daily/*.md','data/daily/*.json'):
            for source in self.root.glob(pattern):
                target=self.checkout/source.relative_to(self.root)
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(source.read_bytes())
        for name in ('state','reports','data'):
            (self.checkout/name).mkdir(exist_ok=True)
        self.git(self.checkout,'add','state','reports','data')
        if not self.git(self.checkout,'status','--porcelain').strip():
            return
        self.git(self.checkout,'commit','-m',message)
        # No force, no silent retry/rebase: a racing writer fails, cannot overwrite history.
        self.git(self.checkout,'push','origin',f'HEAD:refs/heads/{BRANCH}')
