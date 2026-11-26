---
name: Grokbot-RedNote search
description: Use when searching Xiaohongshu / 小红书 / RedNote through the local Grokbot-RedNote service. Always request most-liked (最多点赞) results by default.
---

# Grokbot-RedNote search

Call the local Grokbot-RedNote service. Do not ask the user to type URL parameters.

1. Search with `GET http://127.0.0.1:18765/search?q=KEYWORD&sort=likes`. Always include `sort=likes` so results use Xiaohongshu's Most Liked (最多点赞) order. Do not wait for the user to ask for that ordering, and do not look for trigger phrases.
2. Only omit `sort=likes` or pass `sort=comprehensive` if the user explicitly asks for Comprehensive (综合) order.
3. Bring the returned titles and links back into the conversation.

Do not run a live search only to test this behavior, and do not consume the daily search quota unless the user asked to search.
