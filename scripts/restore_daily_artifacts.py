"""Restore own-repository, main-branch daily artifacts using runner GH_TOKEN."""
import io
import json
import os
import re
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_ARCHIVE = 20_000_000
MAX_MEMBER = 2_000_000


def restore_zip(raw, root, artifact_id):
    if len(raw) > MAX_ARCHIVE:
        raise ValueError('artifact 太大')
    count = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_ARCHIVE:
            raise ValueError('解壓大小超過上限')
        for info in archive.infolist():
            name = Path(info.filename).name
            # Read selected bytes, never extract paths or execute artifact contents.
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}_\d{4}_editor\.md',name):
                continue
            if info.file_size > MAX_MEMBER:
                raise ValueError('素材檔太大')
            folder = root/'reports/daily'
            folder.mkdir(parents=True,exist_ok=True)
            (folder/f'{artifact_id}_{name}').write_bytes(archive.read(info))
            count += 1
    return count


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    root = Path(__file__).resolve().parents[1]
    now = datetime.now(timezone.utc)
    listing = subprocess.run(['gh','api','--paginate','--slurp',f'repos/{repo}/actions/artifacts?per_page=100'],
                             capture_output=True,check=True,timeout=60)
    restored = 0
    for page in json.loads(listing.stdout):
        for artifact in page['artifacts']:
            created = datetime.fromisoformat(artifact['created_at'].replace('Z','+00:00'))
            if artifact['expired'] or not now-timedelta(days=7) <= created <= now:
                continue
            if not re.fullmatch(r'technology-brief-\d+',artifact['name']):
                continue
            if artifact.get('workflow_run',{}).get('head_branch') != 'main':
                continue
            try:
                result = subprocess.run(['gh','api',f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip'],
                                        capture_output=True,check=True,timeout=60)
                restored += restore_zip(result.stdout,root,artifact['id'])
            except (subprocess.SubprocessError,ValueError,OSError,zipfile.BadZipFile) as exc:
                print(f'::warning::daily artifact {artifact["id"]} 無法還原（{type(exc).__name__}）')
    print(f'已還原 {restored} 個 daily report 檔案；無素材時週報會明示資料缺口。')


if __name__ == '__main__':
    main()
