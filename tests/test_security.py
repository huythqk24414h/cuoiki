import unittest
from src.security import redact_public


class PublicBoundaryTests(unittest.TestCase):
    def test_nested_auth_fields_and_embedded_secrets_redacted(self):
        source={'auth':{'accessToken':'DUMMY_TOKEN','api_secret':'DUMMY_SECRET'},
                'rows':[{'source':'SSI','note':'prefix TEST_SECRET suffix','close':'20400'}]}
        result=redact_public(source,['TEST_SECRET'])
        self.assertEqual(result['auth']['accessToken'],'[REDACTED]')
        self.assertEqual(result['auth']['api_secret'],'[REDACTED]')
        self.assertEqual(result['rows'][0]['note'],'prefix [REDACTED] suffix')
        self.assertEqual(result['rows'][0]['close'],'20400')
        self.assertEqual(source['auth']['accessToken'],'DUMMY_TOKEN')

    def test_empty_secret_does_not_corrupt_values(self):
        self.assertEqual(redact_public({'symbol':'SSI','volume':100},['']),{'symbol':'SSI','volume':100})
