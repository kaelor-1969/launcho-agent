from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException

from app import mock_launcho as mock


class MockDraftTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        replacement = patch.object(mock, 'DRAFT_DB', Path(directory.name) / 'drafts.sqlite3')
        replacement.start()
        self.addCleanup(replacement.stop)
        self.token = 'Bearer local-simulation'
        self.payload = mock.DraftRequest(
            kind='shop', businessName='روزا', category='mock-bags-shoes',
            planMonths=3, template='mock-classic', domain={'label': 'roza', 'tld': 'ir'},
        )

    def test_retry_reuses_draft_and_conflicting_payload_is_rejected(self):
        created = mock.create_signup_draft(self.payload, 'request-1', self.token)
        self.assertTrue(created['simulation'])
        self.assertEqual(mock.create_signup_draft(self.payload, 'request-1', self.token), created)
        draft = created['data']
        self.assertEqual(mock.signup_draft_status(draft['ref'], self.token)['data'], draft)
        self.assertEqual(draft['confirmUrl'], f"/signup-drafts/{draft['ref']}/preview")
        self.assertEqual(mock.signup_draft_preview(draft['ref']).status_code, 200)

        with self.assertRaises(HTTPException) as error:
            mock.create_signup_draft(self.payload.model_copy(update={'planMonths': 6}), 'request-1', self.token)
        self.assertEqual(error.exception.status_code, 409)

    def test_expired_draft_cannot_be_reopened_or_recreated_with_the_same_key(self):
        with patch.object(mock, 'DRAFT_TTL', timedelta(seconds=-1)):
            draft = mock.create_signup_draft(self.payload, 'request-1', self.token)['data']
        self.assertEqual(mock.signup_draft_status(draft['ref'], self.token)['data']['status'], 'expired')
        self.assertEqual(mock.signup_draft_preview(draft['ref']).status_code, 410)
        with self.assertRaises(HTTPException) as error:
            mock.create_signup_draft(self.payload, 'request-1', self.token)
        self.assertEqual(error.exception.status_code, 410)
