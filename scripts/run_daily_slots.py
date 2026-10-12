import os
from pathlib import Path
from .history_store import HistoryStore
from src.slot_runner import process_slots


def main():
    root=Path(__file__).resolve().parents[1]
    store=HistoryStore(root)
    store.load()
    outputs=process_slots(root,run_id=os.environ.get('GITHUB_RUN_ID','local'),
                          lookback_hours=int(os.environ.get('LOOKBACK_HOURS','48')),persist=store.publish)
    print(f'完成 {len(outputs)} 個 slots；只有新 slot 會收集，未寄信。')


if __name__=='__main__':
    main()
