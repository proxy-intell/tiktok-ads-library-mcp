"""Self-check for TikTok Ad Library response parsing. No network or API keys needed.

Run: python3 test_parsing.py
"""
from src.services.scrapecreators_service import (
    parse_tiktok_ads,
    pick_best_video_url,
    _format_timestamp,
)

# Shape taken from the ScrapeCreators /v1/tiktok/ad-library/search response.
SEARCH_ADS = [
    {
        "id": "1801234567890123",
        "name": "Spring launch — UGC cut",
        "audit_status": "APPROVED",
        "type": "VIDEO",
        "first_shown_date": 1717200000,
        "last_shown_date": 1719792000,
        "videos": [{"video_url": "https://cdn.tiktok.com/v.mp4?sig=abc", "cover_img": "https://cdn.tiktok.com/c.jpg"}],
        "estimated_audience": "100k-500k",
        "spent": "1k-5k",
        "impression": 421337,
        "image_urls": [],
    },
    {
        "id": "1809999999999999",
        "name": "Static promo",
        "type": "IMAGE",
        "first_shown_date": 1717200000000,  # milliseconds show up on some records
        "last_shown_date": 0,
        "videos": [],
        "image_urls": ["https://cdn.tiktok.com/i.jpg"],
    },
]


def test_parse_search_results():
    parsed = parse_tiktok_ads(SEARCH_ADS)
    assert len(parsed) == 2

    video_ad, image_ad = parsed
    assert video_ad["ad_id"] == "1801234567890123"
    assert video_ad["media_type"] == "video"
    assert video_ad["video_urls"] == ["https://cdn.tiktok.com/v.mp4?sig=abc"]
    assert video_ad["cover_images"] == ["https://cdn.tiktok.com/c.jpg"]
    assert video_ad["impression"] == 421337

    assert image_ad["media_type"] == "image"
    assert image_ad["video_urls"] == []
    assert image_ad["image_urls"] == ["https://cdn.tiktok.com/i.jpg"]


def test_timestamps_handle_seconds_and_millis():
    assert _format_timestamp(1717200000) == "2024-06-01"
    assert _format_timestamp(1717200000000) == "2024-06-01"
    # Missing / zero / non-numeric timestamps must not blow up the parse.
    assert _format_timestamp(0) is None
    assert _format_timestamp(None) is None


def test_malformed_ad_does_not_kill_the_batch():
    parsed = parse_tiktok_ads([{"id": "ok", "videos": [], "image_urls": []}, {"id": "weird", "videos": "not-a-list"}])
    assert [a["ad_id"] for a in parsed] == ["ok"]


def test_pick_best_video_url_ranks_numerically():
    # "1080p" must beat "720p" — lexicographic sort would pick 720p.
    video_info = {"video_url": {"720p": "low.mp4", "1080p": "high.mp4", "480p": "lowest.mp4"}}
    assert pick_best_video_url(video_info) == "high.mp4"
    assert pick_best_video_url({}) is None
    assert pick_best_video_url({"video_url": {}}) is None


if __name__ == "__main__":
    test_parse_search_results()
    test_timestamps_handle_seconds_and_millis()
    test_malformed_ad_does_not_kill_the_batch()
    test_pick_best_video_url_ranks_numerically()
    print("all parsing checks passed")
