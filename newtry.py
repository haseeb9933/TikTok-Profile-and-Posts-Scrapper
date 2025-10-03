import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from TikTokApi import TikTokApi
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TikTok Scraper API")

async def get_api():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    ms_token = "YOUR_MS_TOKEN_HERE"  # Replace with real token
    api = await TikTokApi.create_async(browser, ms_token=ms_token)
    return api, browser, playwright

def extract_hashtags(desc: Optional[str]) -> List[str]:
    if not desc:
        return []
    return re.findall(r'#\w+', desc)

def safe_stat(stats: Dict[str, Any], key: str) -> int:
    value = stats.get(key)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

def resolve_timestamp(video_info: Dict[str, Any]) -> Optional[int]:
    for candidate in ("createTime", "create_time"):
        raw_value = video_info.get(candidate)
        if raw_value in (None, ""):
            continue
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            continue
    return None

@app.get("/profile")
async def scrape_profile(username: str = Query(...), max_posts: int = Query(5, ge=1, le=20)):
    api, browser, playwright = None, None, None
    try:
        api, browser, playwright = await get_api()
        user = await api.user(username=username)
        user_info = await user.info()

        profile = {
            "username": username,
            "bio": user_info.get("signature", ""),
            "followers": user_info.get("followerCount", 0),
            "following": user_info.get("followingCount", 0),
            "likes": user_info.get("heartCount", 0),
            "verified": user_info.get("verified", False),
        }

        posts = []
        async for video in user.videos(count=max_posts):
            try:
                await video.info()
                video_info = video.as_dict
                stats = video_info.get("stats") or {}
                description = video_info.get("desc") or ""
                post = {
                    "post_id": str(video_info.get("id", "")),
                    "likes": safe_stat(stats, "diggCount"),
                    "comments": safe_stat(stats, "commentCount"),
                    "shares": safe_stat(stats, "shareCount"),
                    "views": safe_stat(stats, "playCount"),
                    "timestamp": resolve_timestamp(video_info),
                    "description": description,
                    "hashtags": extract_hashtags(description),
                }
                posts.append(post)
                await asyncio.sleep(2)  # Rate limit
                logger.info(f"Post {post['post_id']}: {post['views']} views")
            except Exception as e:
                logger.error(f"Post error: {e}")
                continue

        return {"profile": profile, "posts": posts}

    except Exception as e:
        logger.error(f"Scrape error: {e}")
        return {"error": str(e)}

    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

# To run: uvicorn newapp:app --reload
