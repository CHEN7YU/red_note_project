"""Quick test: YouTube trending extraction"""
import httpx
import re

print("Fetching YouTube trending...")
r = httpx.get(
    "https://www.youtube.com/feed/trending?gl=US",
    timeout=15,
    follow_redirects=True,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
)
print(f"Status: {r.status_code}, Length: {len(r.text)}")

# Extract titles
m1 = re.findall(r'"title":\{"runs":\[\{"text":"([^"]{5,80})"\}', r.text)
m2 = re.findall(r'"title":\{"simpleText":"([^"]{5,80})"', r.text)
m3 = re.findall(r'"accessibilityData":\{"label":"([^"]{10,120}) by ', r.text)

print(f"Method1 (runs): {len(m1)}")
print(f"Method2 (simpleText): {len(m2)}")
print(f"Method3 (accessibility): {len(m3)}")

# Dedupe
seen = set()
titles = []
for t in m1 + m2 + m3:
    if t not in seen and len(t) > 5:
        seen.add(t)
        titles.append(t)

print(f"\nUnique titles: {len(titles)}")
for i, t in enumerate(titles[:15]):
    print(f"  {i+1}. {t}")

# Also test TikTok Creative Center
print("\n--- TikTok Creative Center ---")
try:
    tr = httpx.get(
        "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list?period=7&limit=20&country_code=US",
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    print(f"Status: {tr.status_code}")
    if tr.status_code == 200:
        data = tr.json()
        print(f"Data keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
        if isinstance(data, dict) and data.get("data"):
            items = data["data"]
            if isinstance(items, dict):
                items = items.get("list", items.get("hashtag_list", []))
            print(f"Items: {len(items)}")
            for item in items[:5]:
                print(f"  {item}")
except Exception as e:
    print(f"ERR: {e}")

# Test other unstable sources
print("\n--- Testing other sources ---")
for name, url in [
    ("vvhan zhihu", "https://api.vvhan.com/api/hotlist/zhihuHot"),
    ("oioweb zhihu", "https://api.oioweb.cn/api/common/HotList?type=zhihu"),
    ("tophub zhihu", "https://tophub.today/n/mproPpoq6O"),
]:
    try:
        r2 = httpx.get(url, timeout=8, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/json,*/*",
        })
        print(f"  {name}: {r2.status_code} len={len(r2.text)}")
    except Exception as e:
        print(f"  {name}: ERR {str(e)[:60]}")
