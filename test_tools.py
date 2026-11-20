"""Tool behaviour through a real MCP client session, with ScrapeCreators stubbed. Run: python test_tools.py"""
import asyncio
import base64
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["PROXY_TELEMETRY"] = "0"
os.environ["SCRAPECREATORS_API_KEY"] = "test"

import requests
from mcp.shared.memory import create_connected_server_and_client_session as connect

from src import ad_history, telemetry
from src.services import media_cache_service, scrapecreators_service

telemetry.STATE_FILE = Path(tempfile.mkdtemp()) / "state.json"
ad_history.HISTORY_FILE = Path(tempfile.mkdtemp()) / "history.json"
media_cache_service.image_cache.get_cached_image = lambda url: None
media_cache_service.image_cache.cache_image = lambda **kw: None
scrapecreators_service.time.sleep = lambda s: None

import mcp_server

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
AD = {"id": "1", "name": "UGC cut", "type": "VIDEO", "first_shown_date": 1700000000, "last_shown_date": 1700500000,
      "videos": [{"video_url": "http://v", "cover_img": "http://c"}], "image_urls": []}


class Resp:
    def __init__(self, status, payload=None, content=b"", content_type="application/json"):
        self.status_code, self._payload, self.content = status, payload, content
        self.headers = {"content-type": content_type}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


calls = []


def fake_get(url, headers=None, params=None, timeout=None):
    calls.append((url, dict(params or {})))
    if "ad-library/search" in url:
        query = params["query"]
        if query == "Flaky":
            first = sum(p.get("query") == "Flaky" for _, p in calls) == 1
            return Resp(502) if first else Resp(200, {"success": True, "advertiser_name": "Flaky", "ads": [AD], "cursor": None, "has_more": False})
        if query == "Broken":
            return Resp(400, {"error": "bad"})
        if query == "Paged":
            if params.get("cursor"):
                return Resp(503)
            return Resp(200, {"success": True, "ads": [AD], "cursor": "c2", "has_more": True})
    return Resp(200, content=PNG, content_type="image/png")


requests.get = fake_get


async def main():
    async with connect(mcp_server.mcp._mcp_server) as c:
        tools = {t.name for t in (await c.list_tools()).tools}
        assert {"search_tiktok_ads", "get_playbook"} <= tools, tools
        assert {p.name for p in (await c.list_prompts()).prompts} == {"script_writing", "competitor_teardown", "competitor_watch"}

        r = await c.call_tool("get_playbook", {"job": "Script writing"})
        assert r.content[0].text.startswith("PLAYBOOK: script_writing")
        p = await c.get_prompt("competitor_watch", {"brief": "Anysphere"})
        assert "My brief: Anysphere" in p.messages[0].content.text

        # A 502 is retried once; a first search seeds the diff baseline.
        r = json.loads((await c.call_tool("search_tiktok_ads", {"query": "Flaky"})).content[0].text)
        assert r["success"] and r["ads"][0]["ad_id"] == "1", r
        assert "baseline saved" in r["changes"]["note"]

        # A continuation page is not diffed.
        r = json.loads((await c.call_tool("search_tiktok_ads", {"query": "Flaky", "cursor": "x"})).content[0].text)
        assert r["changes"] is None

        # A first-page error is reported, not read as "no ads".
        r = json.loads((await c.call_tool("search_tiktok_ads", {"query": "Broken"})).content[0].text)
        assert not r["success"] and "400" in r["error"], r

        # A later-page error keeps the ads already collected and a cursor to resume from.
        r = json.loads((await c.call_tool("search_tiktok_ads", {"query": "Paged", "limit": 5})).content[0].text)
        assert r["success"] and len(r["ads"]) == 1 and r["has_more"] and r["cursor"] == "c2", r

        # The image comes back as an image block the model can see.
        r = await c.call_tool("analyze_ad_image", {"media_url": "http://img", "ad_id": "9"})
        assert [b.type for b in r.content] == ["text", "image"] and not r.isError
        assert "analysis_instructions" in json.loads(r.content[0].text)


asyncio.run(main())

# Diff: first fetch is a baseline, inside 24h keeps it, 24h+ later reports new and dropped.
t0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
ads = lambda *ids: [{"ad_id": i, "first_shown": "2026-10-01"} for i in ids]
assert "baseline saved" in ad_history.changes("k", ads("1", "2"), t0)["note"]
assert "under 24h" in ad_history.changes("k", ads("3"), t0 + timedelta(hours=2))["note"]
later = ad_history.changes("k", ads("2", "3"), t0 + timedelta(days=2))
assert later["new_since_last_fetch"] == ["3"] and later["dropped_since_last_fetch"] == 1 and later["since_last_fetch"] == "2026-11-01"
recent = [{"ad_id": "n", "first_shown": "2026-11-05"}, {"ad_id": "o", "first_shown": "2026-09-01"}]
assert ad_history.launched_recently(recent, t0 + timedelta(days=6)) == ["n"]

print("tool tests passed")
