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
| Moderation events that must not reach Silver | `mod-del-001` (`messageDeletedEvent`), `mod-ban-001` (`userBannedEvent`) |
| A second, concurrent stream with the same spammer and the same viewer text | `SYNTHETIC_LIVE_CHAT_ID_2` (`s2-msg-001`, `s2-msg-002`) |

Expected results (asserted in `tests/test_pipeline_end_to_end.py`): 5 files, 16 raw items,
1 duplicate dropped, 2 moderation events excluded, 13 Silver rows across 2 streams,
2 spam messages (`msg-004`, `msg-005`), 6 Gold authors.
