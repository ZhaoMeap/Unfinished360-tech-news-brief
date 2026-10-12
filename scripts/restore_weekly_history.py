"""Primary weekly restore: durable same-repo branch; artifact fallback is explicit."""
import json
from pathlib import Path
from .history_store import HistoryStore
from .restore_daily_artifacts import main as restore_artifacts


def main():
    root=Path(__file__).resolve().parents[1]
    errors=[]
    try:
        found=HistoryStore(root).load()
        if found:
            print('Restored durable brief-history branch')
            return
        errors.append('brief-history 尚未建立；以 artifact 進行部分還原，缺少 slot ledger')
    except Exception as exc:
        errors.append(f'持久化 history 還原失敗（{type(exc).__name__}）')
    restore_artifacts(initial_errors=errors)


if __name__=='__main__':
    main()
