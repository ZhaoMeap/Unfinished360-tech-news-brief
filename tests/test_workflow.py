"""Protect scheduled editor generation and the explicit manual email gate."""
import unittest
from pathlib import Path


class WorkflowTests(unittest.TestCase):
    def test_editor_schedule_email_gate_and_artifacts(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/daily-brief.yml').read_text()
        self.assertIn("cron: '0 1 * * *'", workflow)
        self.assertIn('default: false', workflow)
        dry = workflow.split('- name: Generate dry-run editor report')[1].split('- name: Explicit email run')[0]
        self.assertIn("github.event_name != 'workflow_dispatch' || !inputs.send_email", dry)
        self.assertIn('run: python -m src.main --dry-run --editor', dry)
        self.assertNotIn('secrets.', dry)
        self.assertNotIn('--send-email', dry)
        email = workflow.split('- name: Explicit email run')[1].split('- uses: actions/upload-artifact')[0]
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.send_email", email)
        self.assertIn('run: python -m src.main --send-email', email)
        self.assertEqual(workflow.count('--send-email'), 1)
        self.assertIn('path: reports/*.md', workflow)
        self.assertIn('retention-days: 7', workflow)
        self.assertIn('if-no-files-found: warn', workflow)
        self.assertIn('name: technology-brief-${{ github.run_id }}', workflow)
