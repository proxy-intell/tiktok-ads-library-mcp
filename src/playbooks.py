"""Analysis playbooks: step-by-step methods for common TikTok ad research jobs.

Served two ways: as MCP prompts (the host's prompt menu) and through the get_playbook tool,
so the model can load one itself. Adapted from hosted Proxy's playbooks to this server's tools.
"""

OTHER_PLATFORMS = (
    "This server covers TikTok's EU ad library only. For Meta, Google or LinkedIn, add the sibling self-hosted servers "
    "(github.com/proxy-intell/facebook-ads-library-mcp, google-ads-library-mcp, linkedin-ads-library-mcp) "
    "or hosted Proxy, which has all four plus keyword search and competitor discovery: "
    "https://useproxy.dev/me/selfhost-tiktok?utm_source=github&utm_medium=playbook&utm_campaign=tiktok-ads-library-mcp"
)

RULES = """\
Rules:
- search_tiktok_ads matches the advertiser's registered business name exactly and case-sensitively, often the legal or parent company ("Anysphere", not "Cursor"). If a brand returns nothing, try the legal name and capitalisation variants before calling it absent.
- The library covers ads delivered in the EU only. Say so when the user's market is elsewhere.
- Ask at most one short question, only if a missing input blocks the work; otherwise state assumptions and go.
- Run time (first_shown to last_shown) is a proxy for performance, not proof. Say "long-running", not "winning". Mark inference ("likely", "suggests").
- A failed lookup is not "no ads": report the error the tool returned.
- End with the deliverables, ready to use. No recap."""

TRIGGERS = {
    "script_writing": "TikTok video ad scripts, hooks to film, UGC briefs, modelling or recreating a winning ad",
    "competitor_teardown": "competitors' TikTok hooks, offers, angles and creative formats",
    "competitor_watch": "tracking competitors on TikTok, what's new since last time, weekly updates",
}

_BODIES = {
    "script_writing": """\
PLAYBOOK: script_writing. Original TikTok-native video scripts built on ads that have run for weeks.
Inputs: product, audience, offer, and 1-3 advertisers in the space. Infer missing ones from the conversation and state them.

Method:
1. search_tiktok_ads(query="<registered advertiser name>", limit=50) per advertiser. Keep video ads with the longest first_shown to last_shown span and a recent last_shown.
2. Pick 3-5 for spread: different hook tactics and formats (talking head, UGC, demo, green screen, voiceover on b-roll), not five cuts of one ad.
3. analyze_ad_video(ad_id="<ad_id>", brand_name="<advertiser>") on each. Always pass ad_id: TikTok media URLs expire.
4. Beat-map each source with seconds per beat: hook 0-2s, problem, mechanism, proof, offer, CTA. Note on-screen text, captions, audio (creator speech, trending sound, produced VO), cut pace, when the product first appears.
5. get_tiktok_ad_details(ad_id="<ad_id>") on the sources you cite, for landing page and targeted countries.

Look for: what the first 2 seconds do (callout, pattern interrupt, visible result, face to camera) and whether line, text and image agree; creator-style versus polished brand production; how fast the problem lands; proof type (demo, number, testimonial, before/after).

Write ORIGINAL scripts for the user's product. Borrow structure and pacing only, never wording, claims or names. Tag claims the user must substantiate [verify].

Output:
- Sources: advertiser, run dates, format, one-line beat map each.
- 3 scripts, 15-34s, vertical 9:16. Per script a table: timecode | spoken line | on-screen text | shot notes. Keep text clear of TikTok's UI safe zones (top caption bar, right action rail, bottom CTA).
- 5 alternative 2-second hooks: opening line, on-screen text, first visual.
- Shoot notes: talent, setting, audio choice, burned-in captions.""",

    "competitor_teardown": """\
PLAYBOOK: competitor_teardown. How competitors sell on TikTok: angles, hooks, offers, formats, gaps.
Inputs: 2-6 competitors (registered advertiser names), the user's own brand if any.

Method:
1. search_tiktok_ads(query="<advertiser>", limit=50) per competitor. Per advertiser: ad count, video vs image mix, oldest first_shown still showing, ads first shown in the last 30 days.
2. Tag every ad: angle (pain, aspiration, social proof, us-vs-them, mechanism, price, urgency, authority), offer (discount, trial, bundle, guarantee, none), style (creator UGC vs brand production).
3. Analyse the 2-3 longest-running ads per advertiser: analyze_ad_video(ad_id="<ad_id>"), or analyze_ad_image(media_url="<cover or image url>") for statics.
4. get_tiktok_ad_details(ad_id="<ad_id>") on the ads you cite, for landing page, targeted countries and engagement.

Look for: angles an advertiser keeps funding for weeks versus ones it tests and kills; one angle across several brands (proven but crowded); creator-led versus brand-led mixes; offers only in new ads; claims nobody makes.

Output:
- Angle x advertiser table: ad count and longest run in days.
- Long-running ads: advertiser, angle, offer, format, run dates.
- Gaps: angles, offers, formats nobody runs.
- 5 angles to test, one line each, tied to an ad or a gap.""",

    "competitor_watch": """\
PLAYBOOK: competitor_watch. What competitors launched, dropped and kept on TikTok since last time.
How the diff works: search_tiktok_ads remembers each advertiser's last fetch (same limit). A re-fetch 24h+ later returns changes.new_since_last_fetch and changes.dropped_since_last_fetch; changes.launched_last_7d lists ads first shown in the last 7 days, even on a first run. The first run is the baseline: say so and report the last-7-day launches.

Method:
1. search_tiktok_ads(query="<advertiser>") per advertiser with the same limit as last time. No cursor: continuation pages are not diffed.
2. Per advertiser: new (ids), dropped (count only), still running (the rest; note long-runners that survived). "Dropped" can also mean an ad fell outside the limit: say so when the fetch hit it.
3. Analyse only the new creatives: analyze_ad_video(ad_id="<ad_id>") or analyze_ad_image(media_url="<cover url>").

Look for: a new hook style or offer; a burst of launches (refresh, scaling, a promo); a mass drop (strategy shift, season end); the same move from several advertisers at once.

Then offer a weekly scheduled task in the user's assistant with a prompt like "Run the competitor_watch playbook for A, B and C with the same settings."

Output per advertiser: launched (count, ids), dropped (count), still running (count, longest-runner), what it suggests (inference). Close with 3 lines: what to respond to and what to ignore.""",
}

PLAYBOOKS = {job: f"{body}\n\n{RULES}\n\n{OTHER_PLATFORMS}" for job, body in _BODIES.items()}
