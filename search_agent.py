import os
import json
import time
import random
import requests
from datetime import datetime

OPENAI_KEY = os.environ["OPENAI_KEY"]
SHEET_URL  = os.environ["SHEET_URL"]
AUTH_TOKEN = os.environ["TWITTER_AUTH_TOKEN"]
CT0        = os.environ["TWITTER_CT0"]
TWID       = os.environ["TWITTER_TWID"]
SEEN_FILE  = "seen_posts.json"

QUERIES = [
    "need ai automation",
    "looking for chatbot developer",
    "hire automation expert",
    "need workflow automation",
    "looking for social media automation"
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def get_headers():
    return {
        "authorization": f"Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "x-csrf-token": CT0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "content-type": "application/json",
        "accept": "*/*",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "cookie": f"auth_token={AUTH_TOKEN}; ct0={CT0}; twid={TWID};"
    }

def search_posts(query):
    try:
        params = {
            "variables": json.dumps({
                "rawQuery": query,
                "count": 10,
                "querySource": "typed_query",
                "product": "Latest",
                "withGrokTranslatedBio": False
            }),
            "features": json.dumps({
                "rweb_video_screen_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "responsive_web_enhance_cards_enabled": False
            })
        }
        r = requests.get(
            "https://x.com/i/api/graphql/qUm8YPFHJWjQ56E_dP4MDg/SearchTimeline",
            headers=get_headers(),
            params=params,
            timeout=15
        )
        print(f"Search '{query}': {r.status_code}")
        if r.status_code != 200:
            return []

        data = r.json()
        posts = []
        instructions = (
            data.get("data", {})
            .get("search_by_raw_query", {})
            .get("search_timeline", {})
            .get("timeline", {})
            .get("instructions", [])
        )
        for instruction in instructions:
            if instruction.get("type") == "TimelineAddEntries":
                for entry in instruction.get("entries", []):
                    try:
                        result = entry["content"]["itemContent"]["tweet_results"]["result"]
                        tweet = result.get("tweet", result)
                        legacy = tweet["legacy"]
                        user = tweet["core"]["user_results"]["result"]["legacy"]

                        # External link
                        urls = legacy.get("entities", {}).get("urls", [])
                        website_url = urls[0].get("expanded_url", "") if urls else ""
                        if "x.com" in website_url or "twitter.com" in website_url:
                            website_url = ""

                        posts.append({
                            "post_url": f"https://x.com/{user['screen_name']}/status/{legacy['id_str']}",
                            "post_title": legacy["full_text"][:80],
                            "post_text": legacy["full_text"],
                            "username": user["screen_name"],
                            "profile_url": f"https://x.com/{user['screen_name']}",
                            "post_datetime": legacy.get("created_at", ""),
                            "location": user.get("location", ""),
                            "website_url": website_url
                        })
                    except (KeyError, TypeError):
                        continue
        return posts
    except Exception as e:
        print(f"Search error: {e}")
        return []

def is_relevant(post_text, query):
    try:
        prompt = f"""You are a lead qualification expert for a digital agency offering:
- AI Automation, Chatbots, Lead Generation
- Social Media Marketing, Content Marketing
- Workflow Automation, N8N, Custom AI Agents

Review this Twitter post and reply ONLY in this format:
score: 7
relevant: yes

Post: {post_text[:300]}
Query: {query}

Score 1-10. relevant: yes or no only."""

        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 20,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=15
        )
        answer = res.json()["choices"][0]["message"]["content"].strip().lower()
        print(f"AI filter: {answer}")
        return "relevant: yes" in answer
    except Exception as e:
        print(f"Filter error: {e}")
        return False

def save_to_sheet(post):
    payload = {
        "A": time.strftime("%Y-%m-%d %H:%M"),
        "B": post.get("post_title", ""),
        "D": post.get("post_text", ""),
        "I": post.get("location", ""),
        "J": "",
        "K": "In Waiting",
        "L": "",
        "M": post.get("post_datetime", ""),
        "O": post.get("profile_url", ""),
        "T": post.get("website_url", "")
    }
    try:
        res = requests.post(SHEET_URL, json=payload, timeout=10)
        print(f"Sheet saved: {post.get('profile_url')} | {res.text}")
    except Exception as e:
        print(f"Sheet error: {e}")

# ============================================================
# MAIN
# ============================================================
seen = load_seen()
print(f"Seen posts: {len(seen)}")

for query in QUERIES:
    time.sleep(random.uniform(3, 6))
    print(f"\nSearching: {query}")
    posts = search_posts(query)
    print(f"Found: {len(posts)} posts")

    for post in posts:
        url = post["post_url"]

        if url in seen:
            print(f"Skip — already seen")
            continue

        if not is_relevant(post["post_text"], query):
            print(f"Not relevant — skip")
            seen.add(url)
            continue

        save_to_sheet(post)
        seen.add(url)
        print(f"Saved: @{post['username']}")
        time.sleep(random.uniform(1, 3))

save_seen(seen)
print("\nDone!")
