"""Quick test: find working image search"""
import httpx
import re

query = "productivity simple todo list"

# Test 1: DuckDuckGo images (returns actual image URLs in HTML)
print("=== DuckDuckGo ===")
ddg_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}&iax=images&ia=images"
r = httpx.get(ddg_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, follow_redirects=True)
print(f"Status: {r.status_code}, Length: {len(r.text)}")
# DDG uses vqd token for image API
vqd = re.findall(r"vqd='([^']+)'", r.text)
if vqd:
    print(f"  vqd token: {vqd[0][:20]}...")
    img_api = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={query.replace(' ', '+')}&vqd={vqd[0]}&f=,,,,,&p=1"
    r2 = httpx.get(img_api, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://duckduckgo.com/"}, timeout=10)
    print(f"  API status: {r2.status_code}")
    if r2.status_code == 200:
        data = r2.json()
        results = data.get("results", [])
        print(f"  Results: {len(results)}")
        for img in results[:3]:
            print(f"    {img.get('image', '')[:80]}")

# Test 2: Google Images (lite mode)
print("\n=== Google Images ===")
g_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&tbm=isch&udm=2"
r3 = httpx.get(g_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=10, follow_redirects=True)
print(f"Status: {r3.status_code}, Length: {len(r3.text)}")
# Google embeds image URLs in data attributes
gimg = re.findall(r'\["(https?://[^"]+\.(?:jpg|jpeg|png|webp))',  r3.text[:100000])
print(f"  Image URLs found: {len(gimg)}")
if gimg:
    for u in gimg[:3]:
        print(f"    {u[:80]}")

# Test 3: Pixabay (free, no API key needed for search page)
print("\n=== Pixabay ===") 
px_url = f"https://pixabay.com/images/search/{query.replace(' ', '%20')}/"
r4 = httpx.get(px_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, follow_redirects=True)
print(f"Status: {r4.status_code}, Length: {len(r4.text)}")
pximg = re.findall(r'src="(https://cdn\.pixabay\.com/photo/[^"]+)"', r4.text[:50000])
print(f"  Image URLs found: {len(pximg)}")
if pximg:
    for u in pximg[:3]:
        print(f"    {u[:80]}")
