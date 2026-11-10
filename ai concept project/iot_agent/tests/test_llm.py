import unittest
from unittest import mock

import httpx
from openai import APITimeoutError

import llm


class LlmTimeoutTests(unittest.TestCase):
    def test_timed_out_requests_are_retried_only_once(self):
        client = mock.Mock()
        client.chat.completions.create.side_effect = APITimeoutError(
            request=httpx.Request("POST", "https://example.invalid"))
        with mock.patch.object(llm, "_get_client", return_value=client), \
                mock.patch.object(llm.time, "sleep"):
            with self.assertRaises(APITimeoutError):
                llm.chat([{"role": "user", "content": "hi"}], use_cache=False)
        self.assertEqual(client.chat.completions.create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
