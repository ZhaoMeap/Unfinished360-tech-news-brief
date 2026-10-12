"""Protect scheduled editor generation and the explicit manual email gate."""
import unittest
from pathlib import Path


class WorkflowTests(unittest.TestCase):
    def test_editor_schedule_email_gate_and_artifacts(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/daily-brief.yml').read_text(encoding="utf-8")
        self.assertIn("cron: '17 1,7,13 * * *'", workflow)
        self.assertIn('default: false', workflow)
        dry = workflow.split('- name: Generate dry-run editor report')[1].split('- name: Explicit email run')[0]
        self.assertIn("github.event_name != 'workflow_dispatch' || (!inputs.send_email && !inputs.editor_preview)", dry)
        self.assertIn('python -m scripts.run_daily_slots', dry)
        self.assertIn('gh auth setup-git',dry)
        self.assertIn('contents: write',workflow)
        self.assertIn('group: technology-brief-history',workflow)
        self.assertNotIn('secrets.SMTP', dry)
        self.assertIn('secrets.OPENAI_API_KEY', dry)
        self.assertNotIn('--send-email', dry)
        self.assertIn('inputs.editor_preview && !inputs.send_email',dry)
        self.assertIn('python -m src.main --dry-run --editor',dry)
        email = workflow.split('- name: Explicit email run')[1].split('- uses: actions/upload-artifact')[0]
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.send_email", email)
        self.assertIn('run: python -m src.main --send-email', email)
        self.assertEqual(workflow.count('--send-email'), 1)
        self.assertIn('path: reports/**/*.md', workflow)
        self.assertIn('retention-days: 7', workflow)
        self.assertIn('if-no-files-found: warn', workflow)
        self.assertIn('name: technology-brief-${{ github.run_id }}', workflow)
