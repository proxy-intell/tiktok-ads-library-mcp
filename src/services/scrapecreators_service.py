import requests
import sys
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# TikTok Ad Library API endpoints
SEARCH_API_URL = "https://api.scrapecreators.com/v1/tiktok/ad-library/search"
AD_DETAILS_API_URL = "https://api.scrapecreators.com/v1/tiktok/ad-library/ad"

# Safety valve so a large `limit` can't page forever
MAX_PAGES = 10

SCRAPECREATORS_API_KEY = None

# --- Custom Exceptions ---

class CreditExhaustedException(Exception):
    """Raised when ScrapeCreators API credits are exhausted."""
    def __init__(self, message: str, credits_remaining: int = 0, topup_url: str = "https://scrapecreators.com/dashboard"):
        self.credits_remaining = credits_remaining
        self.topup_url = topup_url
        super().__init__(message)

class RateLimitException(Exception):
    """Raised when ScrapeCreators API rate limit is exceeded."""
    def __init__(self, message: str, retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(message)

# --- Helper Functions ---

def check_credit_status(response: requests.Response) -> None:
    """
    Raise a descriptive exception when the API refuses a request for billing reasons.

    Args:
        response: HTTP response from ScrapeCreators API

    Raises:
        CreditExhaustedException: If credits are exhausted
        RateLimitException: If rate limit is exceeded
    """
    if response.status_code == 402:  # Payment Required
        raise CreditExhaustedException(
            "ScrapeCreators API credits exhausted. Please top up your account to continue.",
            credits_remaining=0
        )
    if response.status_code == 429:  # Too Many Requests
        retry_after = response.headers.get('retry-after')
        raise RateLimitException(
            "ScrapeCreators API rate limit exceeded. Please wait before making more requests.",
            retry_after=int(retry_after) if retry_after else None
        )
    if response.status_code == 403:  # Forbidden - may indicate credit issues
        try:
            error_data = response.json()
        except ValueError:
            return
        if 'credit' in str(error_data).lower() or 'quota' in str(error_data).lower():
            raise CreditExhaustedException(
                "ScrapeCreators API access denied. This may indicate insufficient credits.",
                credits_remaining=0
            )


def get_scrapecreators_api_key() -> str:
    """
    Get ScrapeCreators API key from command line arguments or environment variable.
    Caches the key in memory after first read.
    Priority: command line argument > environment variable

    Returns:
        str: The ScrapeCreators API key.

    Raises:
        Exception: If no key is provided in command line arguments or environment.
    """
    global SCRAPECREATORS_API_KEY
    if SCRAPECREATORS_API_KEY is None:
        # Try command line argument first
        if "--scrapecreators-api-key" in sys.argv:
            token_index = sys.argv.index("--scrapecreators-api-key") + 1
            if token_index < len(sys.argv):
                SCRAPECREATORS_API_KEY = sys.argv[token_index]
                logger.info("Using ScrapeCreators API key from command line arguments")
            else:
                raise Exception("--scrapecreators-api-key argument provided but no key value followed it")
        # Try environment variable
        elif os.getenv("SCRAPECREATORS_API_KEY"):
            SCRAPECREATORS_API_KEY = os.getenv("SCRAPECREATORS_API_KEY")
            logger.info("Using ScrapeCreators API key from environment variable")
        else:
            raise Exception("ScrapeCreators API key must be provided via '--scrapecreators-api-key' command line argument or 'SCRAPECREATORS_API_KEY' environment variable")

    return SCRAPECREATORS_API_KEY


def _format_timestamp(value: Any) -> Optional[str]:
    """
    Convert a TikTok epoch timestamp into an ISO date string.

    TikTok returns seconds on the ad library endpoints but milliseconds show up on
    some records, so normalise both rather than trusting the unit.
    """
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    seconds = value / 1000 if value > 1e11 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime('%Y-%m-%d')
    except (OverflowError, OSError, ValueError):
        return None


def _request(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Issue an authenticated GET against the ScrapeCreators API and return parsed JSON."""
    api_key = get_scrapecreators_api_key()

    response = requests.get(
        url,
        headers={"x-api-key": api_key},
        params=params,
        timeout=30
    )
    check_credit_status(response)
    response.raise_for_status()

    content = response.json()
    if not content.get('success'):
        raise Exception(f"API returned unsuccessful response: {content}")

    return content


def search_ads(query: str, limit: int = 50, cursor: Optional[str] = None) -> Dict[str, Any]:
    """
    Search the TikTok Ad Library by advertiser name or keyword.

    Pages through results until `limit` ads are collected, the API runs out of
    pages, or MAX_PAGES is hit.

    Args:
        query: Advertiser name (e.g. "Anysphere") or keyword to search for.
        limit: Maximum number of ads to return.
        cursor: Pagination cursor from a previous response.

    Returns:
        Dictionary with parsed `ads`, `cursor`, `has_more`, `total` and `advertiser_name`.

    Raises:
        requests.RequestException: If the API request fails.
        Exception: For other errors.
    """
    if not query or not query.strip():
        raise ValueError("query must be provided")

    ads: List[Dict[str, Any]] = []
    advertiser_name = None
    total = None
    has_more = False
    pages = 0

    while pages < MAX_PAGES:
        params = {"query": query.strip()}
        if cursor:
            params["cursor"] = cursor

        content = _request(SEARCH_API_URL, params)
        pages += 1

        advertiser_name = content.get('advertiser_name') or advertiser_name
        total = content.get('total', total)
        ads.extend(parse_tiktok_ads(content.get('ads', [])))

        cursor = content.get('cursor')
        has_more = bool(content.get('has_more')) and bool(cursor)
        if len(ads) >= limit or not has_more:
            break

    if len(ads) > limit:
        ads = ads[:limit]
        has_more = True

    logger.info(f"Retrieved {len(ads)} TikTok ads for '{query}' across {pages} page(s)")
    return {
        "ads": ads,
        "cursor": cursor,
        "has_more": has_more,
        "total": total,
        "advertiser_name": advertiser_name,
    }


def get_ad_details(ad_id: str) -> Dict[str, Any]:
    """
    Get detailed information for a specific TikTok ad.

    Args:
        ad_id: Ad Library ad ID, Creative Center material ID, or a
               library.tiktok.com detail URL.

    Returns:
        Dictionary containing the raw ad detail payload from the API.

    Raises:
        requests.RequestException: If the API request fails.
        Exception: For other errors.
    """
    if not ad_id or not ad_id.strip():
        raise ValueError("ad_id must be provided")

    content = _request(AD_DETAILS_API_URL, {"ad_id": ad_id.strip()})
    logger.info(f"Retrieved TikTok ad details for {ad_id}")
    return content


def pick_best_video_url(video_info: Dict[str, Any]) -> Optional[str]:
    """
    Pick the highest-resolution playable URL from an ad detail `video_info` block.

    `video_url` is a dict keyed by resolution label (e.g. "720p"). Labels are not
    guaranteed to sort lexicographically, so rank by the leading integer.
    """
    urls = (video_info or {}).get('video_url')
    if not isinstance(urls, dict) or not urls:
        return None

    def resolution_rank(label: str) -> int:
        digits = ''.join(ch for ch in str(label) if ch.isdigit())
        return int(digits) if digits else 0

    best_label = max(urls.keys(), key=resolution_rank)
    return urls[best_label]


def get_fresh_video_url(ad_id: str) -> Optional[str]:
    """
    Re-fetch a playable video URL for an ad.

    TikTok's CDN URLs are signed and expire quickly, so a URL captured from an
    earlier search result is often dead by the time it is analysed. Callers should
    prefer this over reusing a stale `video_url`.
    """
    details = get_ad_details(ad_id)
    return pick_best_video_url(details.get('video_info', {}))


def parse_tiktok_ads(ads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten TikTok Ad Library search results into a consistent shape.

    Args:
        ads: List of raw ad objects from the search endpoint.

    Returns:
        List of parsed ad objects with media URLs surfaced for analysis tools.
    """
    parsed_ads = []

    for ad in ads:
        try:
            videos = ad.get('videos') or []
            image_urls = ad.get('image_urls') or []

            ad_obj = {
                'ad_id': ad.get('id'),
                'name': ad.get('name'),
                'type': ad.get('type'),
                'first_shown': _format_timestamp(ad.get('first_shown_date')),
                'last_shown': _format_timestamp(ad.get('last_shown_date')),
                'first_shown_date': ad.get('first_shown_date'),
                'last_shown_date': ad.get('last_shown_date'),
                'estimated_audience': ad.get('estimated_audience'),
                'spent': ad.get('spent'),
                'impression': ad.get('impression'),
                'audit_status': ad.get('audit_status'),
                'video_urls': [v.get('video_url') for v in videos if v.get('video_url')],
                'cover_images': [v.get('cover_img') for v in videos if v.get('cover_img')],
                'image_urls': image_urls,
                'media_type': 'video' if videos else ('image' if image_urls else 'unknown'),
            }

            parsed_ads.append(ad_obj)

        except Exception as e:
            logger.error(f"Error parsing TikTok ad {ad.get('id', 'unknown')}: {str(e)}")
            continue

    return parsed_ads
