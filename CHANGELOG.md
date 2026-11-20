# Changelog

v1.1.0 · Nov 20 · TikTok

## What's new since last week, and script playbooks

TikTok creatives turn over fast. So this release is about keeping up with them.

### new
- **See what's new since your last pull:** search an advertiser again a day or more later and the result lists its new ads and how many stopped. Ads first shown in the last 7 days show up on the first search too.
- **Playbooks:** video scripts built for TikTok (2-second hooks, 9:16, safe zones), competitor teardowns and a weekly competitor watch. In your client's prompt menu or via `get_playbook`.

### fixed
- **Video analysis works again:** the Gemini model it used was retired. It now defaults to `gemini-3.1-flash-lite`, and `GEMINI_MODEL` in `.env` switches it.
- **Image analysis your AI can see:** `analyze_ad_image` now returns the image, not base64 text.
- **No more keyword searches that return nothing:** the tool told your AI it could search by topic. TikTok only matches exact advertiser names, so it says that now.
- **Searches survive a bad page:** server errors get one retry. If a later page still fails, you keep the ads already found plus a cursor to carry on.

Upgrade: `git pull && ./venv/bin/pip install -r requirements.txt`, then restart your MCP client.

Also self-hosted: [Facebook](https://github.com/proxy-intell/facebook-ads-library-mcp), [Google](https://github.com/proxy-intell/google-ads-library-mcp), [LinkedIn](https://github.com/proxy-intell/linkedin-ads-library-mcp). Or all four in one connection, no keys: [Proxy](https://useproxy.dev/me/selfhost-tiktok?utm_source=github&utm_medium=release&utm_campaign=tiktok-ads-library-mcp).
