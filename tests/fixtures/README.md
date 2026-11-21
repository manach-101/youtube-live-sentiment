# Test fixtures

`raw/youtube_comments_*.json` are **synthetic** pages written by hand. They follow
the documented shape of a YouTube Data API v3 `liveChatMessages.list` response.
They are **not** captured from the real API: every ID, channel and message is invented.

They are designed to exercise edge cases in the pipeline:

| Case | Where |
|------|-------|
| Same message returned by two consecutive polls | `msg-004` appears on pages 1 and 2 |
| Two different channels with the same display name | `UC_synthetic_bob_1` / `UC_synthetic_bob_2` ("Bob") |
| Message without `displayMessage` | `msg-010` |
| Mixed timestamp formats (`Z`, 1/6 fractional digits) | `msg-002`, `msg-003` |
| Repetitive, fast-posting author | `PromoBot` |
| Emoji graphemes | `msg-007` |

Expected results (asserted in `tests/test_pipeline_end_to_end.py`): 12 raw items,
1 duplicate dropped, 11 Silver rows, 2 spam messages, 6 Gold authors.
