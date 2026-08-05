from mcp.server.fastmcp import FastMCP
from src.services.scrapecreators_service import (
    search_ads,
    get_ad_details,
    get_fresh_video_url,
    pick_best_video_url,
    get_scrapecreators_api_key,
)
from src.services.media_cache_service import media_cache, image_cache  # Keep image_cache for backward compatibility
from src.services.gemini_service import configure_gemini, upload_video_to_gemini, analyze_video_with_gemini, cleanup_gemini_file
from typing import Dict, Any, List, Optional
import requests
import base64
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


INSTRUCTIONS = """
This server provides access to TikTok's public Ad Library data through the ScrapeCreators API.
It allows you to search for advertisers and retrieve the ads they are running on TikTok.

Workflow:
1. Use search_tiktok_ads with the registered advertiser name (exact, case-sensitive — e.g. "Anysphere", not "Cursor") or a keyword
2. Use get_tiktok_ad_details with an ad id from the search results for full creative, landing page, and country targeting data
3. Use analyze_ad_image/analyze_ad_video for comprehensive media analysis

TikTok CDN media URLs are signed and expire quickly. Always pass ad_id to analyze_ad_video
so the server can fetch a fresh URL instead of reusing a stale one from an earlier search.
"""


mcp = FastMCP(
   name="TikTok Ads Library",
   instructions=INSTRUCTIONS
)

AD_LIBRARY_URL = "https://library.tiktok.com/ads"


@mcp.tool(
  description="Search TikTok's public Ad Library for the ads an advertiser is running. Use the registered advertiser name (exact, case-sensitive — e.g. 'Anysphere', not 'Cursor'), or a keyword to discover ads by topic. Returns ad ids, run dates, spend/impression bands and media URLs. For complete analysis of visual elements, colors, design, or creative content, you MUST also use analyze_ad_video (passing ad_id) or analyze_ad_image on the media returned by each ad.",
  annotations={
    "title": "Search TikTok Ads",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def search_tiktok_ads(
    query: str,
    limit: Optional[int] = 50,
    cursor: Optional[str] = None
) -> Dict[str, Any]:
    """Search the TikTok Ad Library by advertiser name or keyword.

    TikTok's public Ad Library indexes advertisers by their registered business name,
    which is often not the consumer-facing brand name (e.g. Cursor is registered as
    "Anysphere"). Matching is exact and case-sensitive, so try the legal entity name
    if a brand name returns nothing.

    Args:
        query: Advertiser name or keyword to search for.
        limit: Maximum number of ads to retrieve (default: 50). Results are paged automatically.
        cursor: Pagination cursor from a previous response.

    Returns:
        A dictionary containing:
        - success: Boolean indicating if the ads were retrieved successfully
        - message: Status message describing the result
        - ads: List of ad objects with ad_id, name, dates, spend, impressions and media URLs
        - cursor: Pagination cursor for retrieving additional ads
        - has_more: Whether more ads are available beyond this page
        - total: Total ad count reported by TikTok, if provided
        - error: Error details if the retrieval failed
    """
    if not query or not query.strip():
        return {
            "success": False,
            "message": "Query must be provided and cannot be empty.",
            "ads": [],
            "cursor": None,
            "has_more": False,
            "error": "Missing or empty query"
        }

    try:
        # Get API key first
        get_scrapecreators_api_key()

        result = search_ads(query=query, limit=limit or 50, cursor=cursor)
        ads = result.get('ads', [])

        if not ads:
            return {
                "success": True,
                "message": (
                    f"No ads found for '{query}' in the TikTok Ad Library. "
                    "TikTok indexes advertisers by their registered business name and matches exactly — "
                    "try the legal entity name (e.g. 'Anysphere' for Cursor)."
                ),
                "ads": [],
                "cursor": None,
                "has_more": False,
                "error": None
            }

        advertiser = result.get('advertiser_name') or query
        return {
            "success": True,
            "message": f"Successfully retrieved {len(ads)} TikTok ads for '{advertiser}'.",
            "ads": ads,
            "cursor": result.get('cursor'),
            "has_more": result.get('has_more', False),
            "total": result.get('total'),
            "advertiser_name": result.get('advertiser_name'),
            "ad_library_url": AD_LIBRARY_URL,
            "source_citation": f"[TikTok Ad Library - {advertiser}]({AD_LIBRARY_URL})",
            "error": None
        }

    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Network error while retrieving ads: {str(e)}",
            "ads": [],
            "cursor": None,
            "has_more": False,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to retrieve ads: {str(e)}",
            "ads": [],
            "cursor": None,
            "has_more": False,
            "error": str(e)
        }


@mcp.tool(
  description="Get detailed information about a specific TikTok ad including the full creative, landing page, country targeting, engagement metrics and a fresh playable video URL. Use this with an ad_id from search_tiktok_ads. Essential for analyzing ad content and extracting media URLs for visual analysis.",
  annotations={
    "title": "Get TikTok Ad Details",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def get_tiktok_ad_details(ad_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific TikTok ad.

    Args:
        ad_id: The ad's ID from search_tiktok_ads, a Creative Center material ID,
               or a library.tiktok.com detail URL.

    Returns:
        A dictionary containing:
        - success: Boolean indicating if the details were retrieved successfully
        - ad_title / brand_name: Creative and advertiser identity
        - landing_page: The destination URL for the ad
        - country_code: List of countries the ad was delivered in
        - cost / ctr / like / comment / share: Engagement and performance indicators
        - video_info: Video metadata including duration, cover image and resolutions
        - video_url: Best available playable video URL (freshly signed)
        - error: Error details if the retrieval failed
    """
    if not ad_id or not ad_id.strip():
        return {
            "success": False,
            "message": "Ad ID must be provided and cannot be empty.",
            "error": "Missing or empty ad ID"
        }

    try:
        # Get API key first
        get_scrapecreators_api_key()

        details = get_ad_details(ad_id.strip())
        video_info = details.get('video_info', {}) or {}

        return {
            "success": True,
            "message": f"Successfully retrieved details for TikTok ad {ad_id}.",
            "ad_id": details.get('id', ad_id),
            "ad_title": details.get('ad_title'),
            "brand_name": details.get('brand_name'),
            "landing_page": details.get('landing_page'),
            "country_code": details.get('country_code', []),
            "industry_key": details.get('industry_key'),
            "objective_key": details.get('objective_key'),
            "objectives": details.get('objectives', []),
            "pattern_label": details.get('pattern_label', []),
            "keyword_list": details.get('keyword_list'),
            "highlight_text": details.get('highlight_text'),
            "voice_over": details.get('voice_over'),
            "cost": details.get('cost'),
            "ctr": details.get('ctr'),
            "like": details.get('like'),
            "comment": details.get('comment'),
            "share": details.get('share'),
            "video_info": video_info,
            "video_url": pick_best_video_url(video_info),
            "cover_image": video_info.get('cover'),
            "creative_center_url": details.get('creative_center_url'),
            "ad_library_url": AD_LIBRARY_URL,
            "source_citation": f"[TikTok Ad Details - {details.get('brand_name') or ad_id}]({details.get('creative_center_url') or AD_LIBRARY_URL})",
            "error": None
        }

    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Network error while retrieving ad details: {str(e)}",
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to retrieve ad details: {str(e)}",
            "error": str(e)
        }


@mcp.tool(
  description="REQUIRED for analyzing images from TikTok ads. Download and analyze ad images (cover frames and static creatives) to extract visual elements, text content, colors, people, brand elements, and composition details. This tool should be used for EVERY image URL returned by search_tiktok_ads when doing comprehensive analysis. Uses intelligent caching so multiple image analysis calls are efficient and cost-free.",
  annotations={
    "title": "Analyze Ad Image Content",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def analyze_ad_image(media_url: str, brand_name: Optional[str] = None, ad_id: Optional[str] = None) -> Dict[str, Any]:
    """Download TikTok ad images and prepare them for visual analysis by the MCP client.

    This tool downloads images from TikTok CDN URLs and provides them in a format
    that Claude can analyze using its vision capabilities. Images are cached locally
    to avoid re-downloading. The tool provides detailed analysis instructions to ensure
    comprehensive, objective visual analysis.

    Args:
        media_url: The direct URL to the TikTok ad image (cover_img or image_urls entry).
        brand_name: Optional brand name for cache organization.
        ad_id: Optional ad ID for tracking purposes.

    Returns:
        A dictionary containing:
        - success: Boolean indicating if download was successful
        - message: Status message
        - cached: Boolean indicating if image was retrieved from cache
        - image_data: Base64 encoded image data for vision analysis
        - media_url: Original image URL
        - analysis_instructions: Detailed prompt for objective visual analysis
        - cache_status: Information about cache usage
        - error: Error details if download failed
    """
    if not media_url or not media_url.strip():
        return {
            "success": False,
            "message": "Media URL must be provided and cannot be empty.",
            "cached": False,
            "analysis": {},
            "cache_info": {},
            "error": "Missing or empty media URL"
        }

    try:
        # Check cache first
        cached_data = image_cache.get_cached_image(media_url.strip())

        if cached_data and cached_data.get('analysis_results'):
            # Return cached analysis results
            return {
                "success": True,
                "message": f"Retrieved cached analysis for {media_url}",
                "cached": True,
                "analysis": cached_data['analysis_results'],
                "cache_info": {
                    "cached_at": cached_data.get('downloaded_at'),
                    "analysis_cached_at": cached_data.get('analysis_cached_at'),
                    "file_size": cached_data.get('file_size'),
                    "brand_name": cached_data.get('brand_name'),
                    "ad_id": cached_data.get('ad_id')
                },
                "error": None
            }

        # Determine if we need to download
        image_data = None

        if cached_data:
            # Image is cached but no analysis results yet
            try:
                with open(cached_data['file_path'], 'rb') as f:
                    image_bytes = f.read()
                image_data = base64.b64encode(image_bytes).decode('utf-8')
            except Exception:
                # Cache file corrupted, will re-download
                cached_data = None

        if not cached_data:
            # Download the image
            response = requests.get(media_url.strip(), timeout=30)
            response.raise_for_status()

            # Check if it's an image
            content_type = response.headers.get('content-type', '').lower()
            if not any(img_type in content_type for img_type in ['image/', 'jpeg', 'jpg', 'png', 'gif', 'webp']):
                return {
                    "success": False,
                    "message": f"URL does not point to a valid image. Content type: {content_type}",
                    "cached": False,
                    "analysis": {},
                    "cache_info": {},
                    "error": f"Invalid content type: {content_type}"
                }

            # Cache the downloaded image
            image_cache.cache_image(
                url=media_url.strip(),
                image_data=response.content,
                content_type=content_type,
                brand_name=brand_name,
                ad_id=ad_id
            )

            # Encode for analysis
            image_data = base64.b64encode(response.content).decode('utf-8')

        # Construct comprehensive analysis prompt - let the client control presentation
        analysis_prompt = """
Analyze this TikTok ad image and extract ALL factual information about:

**Overall Visual Description:**
- Complete description of what is shown in the image

**Text Elements:**
- Identify and transcribe ALL text present in the image
- Categorize each text element as:
  * "Headline Hook" (designed to grab attention)
  * "Value Proposition" (explains the benefit to the viewer)
  * "Call to Action (CTA)" (tells the viewer what to do next)
  * "Referral" (prompts the viewer to share the product)
  * "Disclaimer" (legal text, terms, conditions)
  * "Brand Name" (company or product names)
  * "Other" (any other text)
- Note whether text looks like native TikTok UI/caption styling or a designed overlay

**People Description:**
- For each person visible: age range, gender, appearance, clothing, pose, facial expression, setting

**Brand Elements:**
- Logos present (describe and position)
- Product shots (describe what products are shown)
- Brand colors or visual identity elements

**Composition & Layout:**
- Layout structure (grid, asymmetrical, centered, etc.)
- Visual hierarchy (what draws attention first, second, third)
- Element positioning (top-left, center, bottom-right, etc.)
- Safe-zone awareness: whether key elements sit clear of TikTok's UI overlays (top caption bar, right action rail, bottom CTA)
- Use of composition techniques (rule of thirds, leading lines, symmetry, etc.)

**Colors & Visual Style:**
- List ALL dominant colors (specific color names or hex codes if possible)
- Background color/type and style
- Photography style (professional, candid, studio, lifestyle, UGC, etc.)
- Any filters, effects, or styling applied

**Technical & Target Audience Indicators:**
- Image format and aspect ratio (note whether it is vertical 9:16 native or a repurposed landscape/square asset)
- Text readability and contrast
- Overall image quality
- Visual cues about target audience (age, lifestyle, interests, demographics)
- Setting/environment details

**Message & Theme:**
- What story or message the visual conveys
- Emotional tone and mood
- Marketing strategy indicators
- Whether the creative reads as polished brand advertising or creator-style UGC

Extract ALL this information comprehensively. The presentation format (summary vs detailed breakdown) will be determined based on the user's specific request context.
"""

        result = {
            "success": True,
            "message": "Image downloaded and ready for analysis.",
            "cached": bool(cached_data),
            "image_data": image_data,
            "media_url": media_url,
            "brand_name": brand_name,
            "ad_id": ad_id,
            "analysis_instructions": analysis_prompt,
            "ad_library_url": AD_LIBRARY_URL,
            "source_citation": f"[TikTok Ad Library - {brand_name if brand_name else 'Ad'} #{ad_id if ad_id else 'Unknown'}]({media_url})",
            "cache_status": "Used cached image" if cached_data else "Downloaded and cached new image",
            "error": None
        }

        return result

    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Failed to download image from {media_url}: {str(e)}",
            "cached": False,
            "analysis": {},
            "cache_info": {},
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to process image from {media_url}: {str(e)}",
            "cached": False,
            "analysis": {},
            "cache_info": {},
            "error": str(e)
        }


@mcp.tool(
  description="REQUIRED for checking media cache status and storage usage. Use this tool when users ask about cache statistics, storage space used by cached media (images and videos), or how many files have been analyzed and cached. Essential for cache management and monitoring.",
  annotations={
    "title": "Get Media Cache Statistics",
    "readOnlyHint": True,
    "openWorldHint": False
  }
)
def get_cache_stats() -> Dict[str, Any]:
    """Get comprehensive statistics about the media cache (images and videos).

    Returns:
        A dictionary containing:
        - success: Boolean indicating if stats were retrieved successfully
        - message: Status message
        - stats: Cache statistics including:
            * total_files: Total number of cached files
            * total_images: Number of cached images
            * total_videos: Number of cached videos
            * total_size_mb/gb: Storage space used
            * analyzed_files: Number of files with cached analysis
            * unique_brands: Number of different brands cached
        - error: Error details if retrieval failed
    """
    try:
        stats = media_cache.get_cache_stats()

        total_files = stats.get('total_files', 0)
        total_images = stats.get('total_images', 0)
        total_videos = stats.get('total_videos', 0)

        return {
            "success": True,
            "message": f"Cache contains {total_files} files ({total_images} images, {total_videos} videos) using {stats.get('total_size_gb', 0)}GB storage",
            "stats": stats,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to retrieve cache statistics: {str(e)}",
            "stats": {},
            "error": str(e)
        }


@mcp.tool(
  description="REQUIRED for finding previously analyzed ad media (images and videos) in cache. Use this tool when users want to search for cached media by brand name, find media with people, search by colors, or filter by media type. Essential for retrieving past analysis results without re-downloading media.",
  annotations={
    "title": "Search Cached Media",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def search_cached_media(
    brand_name: Optional[str] = None,
    has_people: Optional[bool] = None,
    color_contains: Optional[str] = None,
    media_type: Optional[str] = None,
    limit: Optional[int] = 20
) -> Dict[str, Any]:
    """Search cached media (images and videos) by various criteria.

    Args:
        brand_name: Filter by exact brand name match
        has_people: Filter by presence of people in media (True/False)
        color_contains: Filter by dominant color (partial match, e.g., "red", "blue")
        media_type: Filter by media type ('image' or 'video')
        limit: Maximum number of results to return (default: 20)

    Returns:
        A dictionary containing:
        - success: Boolean indicating if search was successful
        - message: Status message
        - results: List of matching cached media with metadata
        - count: Number of results returned
        - error: Error details if search failed
    """
    try:
        results = media_cache.search_cached_media(
            brand_name=brand_name,
            has_people=has_people,
            color_contains=color_contains,
            media_type=media_type
        )

        # Limit results
        if limit and len(results) > limit:
            results = results[:limit]

        # Remove large base64 data from results for cleaner output
        clean_results = []
        for result in results:
            clean_result = result.copy()
            if 'analysis_results' in clean_result and clean_result['analysis_results']:
                # Keep analysis but remove any base64 image data if present
                analysis = clean_result['analysis_results'].copy()
                if 'image_data_base64' in analysis:
                    analysis['image_data_base64'] = "[Image data available]"
                clean_result['analysis_results'] = analysis
            clean_results.append(clean_result)

        search_criteria = []
        if brand_name:
            search_criteria.append(f"brand: {brand_name}")
        if has_people is not None:
            search_criteria.append(f"has_people: {has_people}")
        if color_contains:
            search_criteria.append(f"color: {color_contains}")
        if media_type:
            search_criteria.append(f"media_type: {media_type}")

        criteria_str = ", ".join(search_criteria) if search_criteria else "no filters"

        return {
            "success": True,
            "message": f"Found {len(clean_results)} cached media files matching criteria: {criteria_str}",
            "results": clean_results,
            "count": len(clean_results),
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to search cached media: {str(e)}",
            "results": [],
            "count": 0,
            "error": str(e)
        }


@mcp.tool(
  description="REQUIRED for cleaning up old cached media files (images and videos) and freeing disk space. Use this tool when users want to remove old cached media, clean up storage space, or when cache becomes too large. Essential for cache maintenance and storage management.",
  annotations={
    "title": "Cleanup Media Cache",
    "readOnlyHint": False,
    "openWorldHint": False
  }
)
def cleanup_media_cache(max_age_days: Optional[int] = 30) -> Dict[str, Any]:
    """Clean up old cached media files (images and videos) and database entries.

    Args:
        max_age_days: Maximum age in days before media files are deleted (default: 30)

    Returns:
        A dictionary containing:
        - success: Boolean indicating if cleanup was successful
        - message: Status message with cleanup results
        - cleanup_stats: Statistics about what was cleaned up
        - error: Error details if cleanup failed
    """
    try:
        # Get stats before cleanup
        stats_before = media_cache.get_cache_stats()

        # Perform cleanup
        media_cache.cleanup_old_cache(max_age_days=max_age_days or 30)

        # Get stats after cleanup
        stats_after = media_cache.get_cache_stats()

        files_removed = stats_before.get('total_files', 0) - stats_after.get('total_files', 0)
        images_removed = stats_before.get('total_images', 0) - stats_after.get('total_images', 0)
        videos_removed = stats_before.get('total_videos', 0) - stats_after.get('total_videos', 0)
        space_freed_mb = stats_before.get('total_size_mb', 0) - stats_after.get('total_size_mb', 0)

        return {
            "success": True,
            "message": f"Cleanup completed: removed {files_removed} files ({images_removed} images, {videos_removed} videos), freed {space_freed_mb:.2f}MB",
            "cleanup_stats": {
                "total_files_removed": files_removed,
                "images_removed": images_removed,
                "videos_removed": videos_removed,
                "space_freed_mb": round(space_freed_mb, 2),
                "max_age_days": max_age_days or 30,
                "files_remaining": stats_after.get('total_files', 0),
                "images_remaining": stats_after.get('total_images', 0),
                "videos_remaining": stats_after.get('total_videos', 0),
                "space_remaining_mb": stats_after.get('total_size_mb', 0)
            },
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to cleanup cache: {str(e)}",
            "cleanup_stats": {},
            "error": str(e)
        }


# Backward compatibility aliases
def search_cached_images(brand_name: Optional[str] = None, has_people: Optional[bool] = None,
                        color_contains: Optional[str] = None, limit: Optional[int] = 20) -> Dict[str, Any]:
    """Search cached images by criteria (backward compatibility)."""
    return search_cached_media(brand_name, has_people, color_contains, 'image', limit)

cleanup_image_cache = cleanup_media_cache


VIDEO_ANALYSIS_PROMPT = """
Analyze this TikTok ad video and provide a comprehensive, structured breakdown following this exact format:

**SCENE ANALYSIS:**
Analyze the video at a scene-by-scene level. For each identified scene, provide:

Scene [Number]: [Brief scene title]
1. Visual Description:
   - Detailed description of key visuals within the scene
   - Appearance and demographics of featured individuals (age, gender, notable characteristics)
   - Specific camera angles and movements used (handheld/selfie/static/tracking)

2. Text Elements:
   - Document ALL text elements appearing in the scene, including burned-in captions and native-style text stickers
   - Categorize each text element as:
     * "Text Hook" (introductory text designed to grab attention)
     * "CTA (middle)" (call-to-action appearing mid-video)
     * "CTA (end)" (final call-to-action)

3. Brand Elements:
   - Note any visible brand logos or product placements
   - Provide brief descriptions and specific timing within the scene

4. Audio Analysis:
   - Transcription or detailed summary of any voiceover present
   - Describe voiceover characteristics: tone, pitch, conveyed emotions
   - Identify and briefly describe notable sound effects
   - Note whether audio is original creator speech, a trending sound, or a produced VO

5. Music Analysis:
   - Music present: [true/false]
   - If true: Brief description or identification of music style/track, and whether it sounds like a TikTok trending audio

6. Scene Transition:
   - Describe the style and pacing of transition to next scene (quick cuts, fades, jump cuts, dynamic transitions, etc.)

**OVERALL VIDEO ANALYSIS:**

**Ad Format:**
- Identify the specific ad format (In-Feed, Spark Ad / creator-style, TopView, branded content, etc.)
- Aspect ratio and orientation (note if it is native vertical 9:16 or a repurposed asset)
- Duration and pacing style

**Creator vs Brand Style:**
- Does this read as polished brand production or creator-style UGC?
- Evidence for the assessment (framing, lighting, audio, delivery)

**Notable Angles:**
- List all significant camera angles used throughout the video
- Comment on their effectiveness and purpose

**Overall Messaging:**
- Primary message or value proposition
- Secondary messages or supporting points
- Target audience indicators

**Hook Analysis:**
- Primary hook type: Text, Visual, or VoiceOver
- What happens in the first 3 seconds specifically
- Effectiveness assessment of attention-grabbing elements

Provide detailed, factual observations that would help understand the video's marketing strategy and effectiveness. Focus on specific, actionable insights.
"""


@mcp.tool(
  description="REQUIRED for analyzing video ads from TikTok. Downloads and analyzes ad videos using Gemini's video understanding to extract the hook, scene-by-scene storytelling, on-screen text, audio/voiceover, pacing and brand messaging. ALWAYS pass ad_id — TikTok CDN URLs are signed and expire within minutes, and ad_id lets the server fetch a fresh URL and cache results stably across sessions. Uses intelligent caching for efficiency.",
  annotations={
    "title": "Analyze Ad Video Content",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def analyze_ad_video(ad_id: Optional[str] = None, media_url: Optional[str] = None, brand_name: Optional[str] = None) -> Dict[str, Any]:
    """Download TikTok ad videos and analyze them using Gemini's video understanding capabilities.

    Prefer passing ad_id: TikTok's CDN URLs are signed and short-lived, so a
    video_url captured from an earlier search_tiktok_ads call is usually dead by
    the time it reaches this tool. With ad_id the server re-fetches a fresh URL,
    and caches under a stable key so repeat analysis is free.

    Args:
        ad_id: The TikTok ad ID from search_tiktok_ads. Strongly preferred.
        media_url: Direct video URL. Used only when ad_id is not supplied, or as
                   the first attempt before falling back to a refreshed URL.
        brand_name: Optional brand name for cache organization.

    Returns:
        A dictionary containing:
        - success: Boolean indicating if analysis was successful
        - message: Status message
        - cached: Boolean indicating if the analysis came from cache
        - analysis: Comprehensive video analysis results
        - media_url: The URL actually downloaded
        - cache_status: Information about cache usage
        - error: Error details if analysis failed
    """
    if not ad_id and not media_url:
        return {
            "success": False,
            "message": "Either ad_id or media_url must be provided. Prefer ad_id — TikTok media URLs expire quickly.",
            "cached": False,
            "analysis": {},
            "cache_info": {},
            "error": "Missing ad_id and media_url"
        }

    ad_id = ad_id.strip() if ad_id else None
    media_url = media_url.strip() if media_url else None

    # Cache under the ad id when we have one. TikTok signs and rotates its CDN
    # URLs, so a URL-keyed cache would never hit on a second look at the same ad.
    cache_key = f"tiktok:ad:{ad_id}" if ad_id else media_url

    cached_data = None
    gemini_file = None
    try:
        cached_data = media_cache.get_cached_media(cache_key, media_type='video')

        if cached_data and cached_data.get('analysis_results'):
            return {
                "success": True,
                "message": f"Retrieved cached video analysis for {ad_id or media_url}",
                "cached": True,
                "analysis": cached_data['analysis_results'],
                "cache_info": {
                    "cached_at": cached_data.get('downloaded_at'),
                    "analysis_cached_at": cached_data.get('analysis_cached_at'),
                    "file_size": cached_data.get('file_size'),
                    "brand_name": cached_data.get('brand_name'),
                    "ad_id": cached_data.get('ad_id'),
                    "duration_seconds": cached_data.get('duration_seconds')
                },
                "ad_library_url": AD_LIBRARY_URL,
                "source_citation": f"[TikTok Ad Library - {brand_name if brand_name else 'Ad'} #{ad_id if ad_id else 'Unknown'}]({AD_LIBRARY_URL})",
                "error": None
            }

        video_path = None
        file_size = None
        duration_seconds = None
        content_type = None

        if cached_data:
            # Video is cached but no analysis results yet
            video_path = cached_data['file_path']
            file_size = cached_data['file_size']
            duration_seconds = cached_data.get('duration_seconds')
            content_type = cached_data.get('content_type')
        else:
            get_scrapecreators_api_key()

            # Resolve a playable URL, refreshing through the API when the cached
            # or caller-supplied URL has already expired.
            response = None
            if media_url:
                try:
                    response = requests.get(media_url, timeout=60)
                    response.raise_for_status()
                except requests.exceptions.RequestException:
                    if not ad_id:
                        raise
                    response = None

            if response is None:
                fresh_url = get_fresh_video_url(ad_id)
                if not fresh_url:
                    return {
                        "success": False,
                        "message": f"No playable video URL found for TikTok ad {ad_id}. The ad may be image-only.",
                        "cached": False,
                        "analysis": {},
                        "cache_info": {},
                        "error": "No video URL in ad details"
                    }
                media_url = fresh_url
                response = requests.get(media_url, timeout=60)
                response.raise_for_status()

            content_type = response.headers.get('content-type', '').lower()
            if not any(vid_type in content_type for vid_type in ['video/', 'mp4', 'mov', 'webm', 'avi']):
                return {
                    "success": False,
                    "message": f"URL does not point to a valid video. Content type: {content_type}",
                    "cached": False,
                    "analysis": {},
                    "cache_info": {},
                    "error": f"Invalid content type: {content_type}"
                }

            video_path = media_cache.cache_media(
                url=cache_key,
                media_data=response.content,
                content_type=content_type,
                media_type='video',
                brand_name=brand_name,
                ad_id=ad_id
            )
            file_size = len(response.content)

        # Configure Gemini API
        try:
            client = configure_gemini()
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to configure Gemini API: {str(e)}. Ensure --gemini-api-key is provided or GEMINI_API_KEY environment variable is set.",
                "cached": bool(cached_data),
                "analysis": {},
                "cache_info": {},
                "error": f"Gemini configuration error: {str(e)}"
            }

        # Upload video to Gemini and analyze
        gemini_file = upload_video_to_gemini(client, video_path)
        analysis_text = analyze_video_with_gemini(client, gemini_file, VIDEO_ANALYSIS_PROMPT)

        analysis_results = {
            "raw_analysis": analysis_text,
            "model_used": os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
            "video_metadata": {
                "file_size_mb": round(file_size / (1024 * 1024), 2) if file_size else None,
                "duration_seconds": duration_seconds,
                "content_type": content_type
            }
        }

        media_cache.update_analysis_results(cache_key, analysis_results)
        cleanup_gemini_file(client, gemini_file.name)
        gemini_file = None

        return {
            "success": True,
            "message": "Video analysis completed successfully",
            "cached": bool(cached_data),
            "analysis": analysis_results,
            "media_url": media_url,
            "brand_name": brand_name,
            "ad_id": ad_id,
            "cache_status": "Used cached video" if cached_data else "Downloaded and cached new video",
            "ad_library_url": AD_LIBRARY_URL,
            "source_citation": f"[TikTok Ad Library - {brand_name if brand_name else 'Ad'} #{ad_id if ad_id else 'Unknown'}]({AD_LIBRARY_URL})",
            "error": None
        }

    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Failed to download video for {ad_id or media_url}: {str(e)}",
            "cached": False,
            "analysis": {},
            "cache_info": {},
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to analyze video for {ad_id or media_url}: {str(e)}",
            "cached": bool(cached_data),
            "analysis": {},
            "cache_info": {},
            "error": str(e)
        }
    finally:
        # Gemini file uploads are billed storage; drop them even on the error path.
        if gemini_file is not None:
            try:
                cleanup_gemini_file(configure_gemini(), gemini_file.name)
            except Exception:
                pass


if __name__ == "__main__":
   mcp.run()
