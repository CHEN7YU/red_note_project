# -*- coding: utf-8 -*-
"""
pipeline/publisher_x.py
========================
X/Twitter auto-publisher using tweepy (OAuth 1.0a, Free tier).
Supports text tweets and text+image tweets.
"""

import os
from pathlib import Path

from .config import ROOT_DIR


def _load_keys() -> dict:
    """Load X API keys from .env"""
    env_file = ROOT_DIR / ".env"
    keys = {}
    if env_file.exists():
        for line in open(env_file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                keys[k.strip()] = v.strip()
    for k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET", "X_BEARER_TOKEN"]:
        if k not in keys or not keys[k]:
            keys[k] = os.environ.get(k, "")
    return keys


def post_tweet(text: str, image_path: str = None) -> dict:
    """
    Post a tweet to X/Twitter.
    Args:
        text: Tweet text (max 280 chars)
        image_path: Optional image file path
    Returns:
        {"success": bool, "tweet_id": str, "url": str, "error": str}
    """
    try:
        import tweepy
    except ImportError:
        return {"success": False, "error": "tweepy not installed. Run: pip install tweepy"}

    keys = _load_keys()
    if not keys.get("X_API_KEY") or not keys.get("X_ACCESS_TOKEN"):
        return {"success": False, "error": "X API keys not configured in .env"}

    if len(text) > 280:
        text = text[:277] + "..."

    try:
        # v1.1 API for media upload
        auth = tweepy.OAuth1UserHandler(
            keys["X_API_KEY"],
            keys["X_API_SECRET"],
            keys["X_ACCESS_TOKEN"],
            keys["X_ACCESS_TOKEN_SECRET"],
        )
        api_v1 = tweepy.API(auth)

        # v2 client for tweet creation
        client = tweepy.Client(
            consumer_key=keys["X_API_KEY"],
            consumer_secret=keys["X_API_SECRET"],
            access_token=keys["X_ACCESS_TOKEN"],
            access_token_secret=keys["X_ACCESS_TOKEN_SECRET"],
        )

        media_id = None
        if image_path and os.path.isfile(image_path):
            media = api_v1.media_upload(filename=image_path)
            media_id = media.media_id_string
            print(f"  📷 图片上传: {media_id}")

        if media_id:
            response = client.create_tweet(text=text, media_ids=[media_id])
        else:
            response = client.create_tweet(text=text)

        tweet_id = response.data.get("id", "")
        return {
            "success": True,
            "tweet_id": tweet_id,
            "url": f"https://x.com/i/status/{tweet_id}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}
