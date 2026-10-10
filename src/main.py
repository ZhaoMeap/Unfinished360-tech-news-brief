"""Run with python -m src.main; no argument means dry-run."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from .fetch_sources import fetch_sources
from .fetch_links import fetch_links, read_links
from .community import collect_community
from .render_report import render_report
from .editor_report import render_editor_report
from .send_email import send_email

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="還沒想到科技快報（預設 dry-run）")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="只產出 Markdown，不寄信")
    modes.add_argument("--send-email", action="store_true", help="產出報告，並以 SMTP 寄信")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--links", type=Path, help="指定連結檔，每行一個 HTTPS URL")
    inputs.add_argument("--editor", action="store_true", help="根據自動候選產生每日編輯簡報")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    try:
        results = fetch_links(read_links(args.links)) if args.links else fetch_sources()
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"連結檔錯誤（{type(exc).__name__}）；請提供 1–20 個有效 HTTPS URL。")
        return 1
    for result in results:
        print(f"{result.source}：{result.status}")
    discussions = collect_community(results)
    if args.editor:
        path, subject, body = render_editor_report(results, ROOT / "reports", discussions=discussions)
    else:
        path, subject, body = render_report(results, ROOT / "reports", mode="links" if args.links else "radar", discussions=discussions)
    print(f"報告已產出：{path}")
    if args.editor and args.send_email:
        print("Editor Mode 僅產生報告，忽略 --send-email；未寄信。")
        return 0
    if args.send_email:
        return 0 if send_email(subject, body) else 1
    print("dry-run：未寄信。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
