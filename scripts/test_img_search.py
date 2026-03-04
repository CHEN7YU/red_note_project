# -*- coding: utf-8 -*-
"""Test: find a working image search approach"""
import httpx
import re
import json
import base64

query = "LinkedIn job search tips productivity"

# Approach: Google Images with specific parameters that return thumbnails in HTML
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

print("=== Approach 1: Google tbm=isch (thumbnail extraction) ===")
g_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&tbm=isch"
r = httpx.get(g_url, headers=headers, timeout=15, follow_redirects=True)
print(f"Status: {r.status_code}, Length: {len(r.text)}")

# Google embeds image data in a script tag like: AF_initDataCallback({...data...})
# Look for image URLs in the initial data
img_matches = re.findall(r'\["(https?://[^"]+)",\d+,\d+\]', r.text)
print(f"Image URLs (raw): {len(img_matches)}")
# Filter to actual images (not google/gstatic)
real_imgs = [u for u in img_matches if not any(x in u for x in ['google.com', 'gstatic.com', 'youtube.com', 'schema.org'])]
print(f"Image URLs (filtered): {len(real_imgs)}")
for u in real_imgs[:5]:
    print(f"  {u[:100]}")

print("\n=== Approach 2: Serpapi-style scraping ===")
# Look for data encoded differently
data_urls = re.findall(r'data:image/[^"]+', r.text[:200000])
print(f"Data URLs (base64 thumbnails): {len(data_urls)}")

print("\n=== Approach 3: Extract from AF_initDataCallback ===")
# Google puts image URLs in a specific callback format
cb_matches = re.findall(r'"(https?://[^"]{20,}\.(?:jpg|jpeg|png|webp)[^"]*)"', r.text)
cb_filtered = [u for u in cb_matches if not any(x in u for x in ['google', 'gstatic', 'googleapis', 'schema'])]
# Dedupe
seen = set()
cb_unique = []
for u in cb_filtered:
    short = u.split('?')[0]
    if short not in seen:
        seen.add(short)
        cb_unique.append(u)
print(f"Callback image URLs: {len(cb_unique)}")
for u in cb_unique[:5]:
    print(f"  {u[:120]}")

# Try downloading one
if cb_unique:
    print("\n=== Download test ===")
    test_url = cb_unique[0]
    try:
        r2 = httpx.get(test_url, headers=headers, timeout=10, follow_redirects=True)
        print(f"Download: status={r2.status_code}, size={len(r2.content)}B, content-type={r2.headers.get('content-type','?')}")
        if r2.status_code == 200 and len(r2.content) > 1000:
            with open("output/_test_download.jpg", "wb") as f:
                f.write(r2.content)
            print("Saved to output/_test_download.jpg")
    except Exception as e:
        print(f"Download failed: {e}")
