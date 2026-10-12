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


def main(initial_errors=None):
    repo = os.environ['GITHUB_REPOSITORY']
    root = Path(__file__).resolve().parents[1]
    now = datetime.now(timezone.utc)
    errors=list(initial_errors or [])
    restored=0
    status_path=root/'state/restore_status.json'
    status_path.parent.mkdir(parents=True,exist_ok=True)
    try:
        listing = subprocess.run(['gh','api','--paginate','--slurp',f'repos/{repo}/actions/artifacts?per_page=100'],
                             capture_output=True,check=True,timeout=60)
    except (subprocess.SubprocessError,OSError) as exc:
        errors.append(f'Artifact 列表無法讀取（{type(exc).__name__}）')
        status_path.write_text(json.dumps(dict(restored=0,errors=errors,fatal=True),ensure_ascii=False),encoding='utf-8')
        raise RuntimeError('Artifact listing unavailable; partial status saved') from exc
    try:
        pages = json.loads(listing.stdout)
        if not isinstance(pages, list) or any(not isinstance(page, dict) or not isinstance(page.get('artifacts'), list) for page in pages):
            raise ValueError('invalid artifact listing')
    except (ValueError, TypeError) as exc:
        errors.append('Artifact 列表格式無效')
        status_path.write_text(json.dumps(dict(restored=0,errors=errors,fatal=True),ensure_ascii=False),encoding='utf-8')
        raise RuntimeError('Invalid artifact listing; partial status saved') from exc
    for page in pages:
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
                errors.append(f'Artifact {artifact["id"]} 還原失敗（{type(exc).__name__}）')
                print(f'::warning::daily artifact {artifact["id"]} 無法還原（{type(exc).__name__}）')
    status_path.write_text(json.dumps(dict(restored=restored,errors=errors,fatal=bool(errors) and restored==0),ensure_ascii=False),encoding='utf-8')
    if errors and restored==0:
        raise RuntimeError('No safe artifact data restored; partial status saved')
    print(f'已還原 {restored} 個 daily report 檔案；無素材時週報會明示資料缺口。')


if __name__ == '__main__':
    main()
