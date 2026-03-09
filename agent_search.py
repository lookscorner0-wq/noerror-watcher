import asyncio
import json
import os
import random
import requests
import time
from playwright.async_api import async_playwright

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

async def search_and_save():
    seen = load_seen()
    print(f"Seen posts: {len(seen)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        )
        context = await browser.new_context()
        await context.add_cookies([
            {"name": "auth_token", "value": AUTH_TOKEN, "domain": ".x.com", "path": "/"},
            {"name": "ct0", "value": CT0, "domain": ".x.com", "path": "/"},
            {"name": "twid", "value": TWID, "domain": ".x.com", "path": "/"},
        ])
        page = await context.new_page()
        page.set_default_timeout(30000)

        for query in QUERIES:
            print(f"\nSearching: {query}")
            try:
                q = query.replace(" ", "+")
                await page.goto(
                    f"https://x.com/search?q={q}&f=live",
                    timeout=30000
                )
                await page.wait_for_timeout(8000)
                await page.evaluate("window.scrollBy(0, 500)")
                await page.wait_for_timeout(3000)

                tweets = await page.query_selector_all('article[data-testid="tweet"]')
                print(f"Found: {len(tweets)} tweets")

                for tweet in tweets:
                    try:
                        link_el = await tweet.query_selector('a[href*="/status/"]')
                        link = await link_el.get_attribute("href") if link_el else ""
                        post_url = f"https://x.com{link}" if link else ""

                        if not post_url or post_url in seen:
                            continue

                        text_el = await tweet.query_selector('[data-testid="tweetText"]')
                        text = await text_el.inner_text() if text_el else ""

                        user_el = await tweet.query_selector('[data-testid="User-Name"]')
                        user_text = await user_el.inner_text() if user_el else ""
                        username = user_text.split("\n")[1] if "\n" in user_text else user_text
                        profile_url = f"https://x.com/{username.replace('@', '')}"

                        time_el = await tweet.query_selector("time")
                        post_datetime = await time_el.get_attribute("datetime") if time_el else ""

                        ext_el = await tweet.query_selector('a[href*="http"]:not([href*="x.com"]):not([href*="twitter.com"])')
                        website_url = await ext_el.get_attribute("href") if ext_el else ""

                        user_loc_el = await tweet.query_selector('[data-testid="UserLocation"]')
                        location = await user_loc_el.inner_text() if user_loc_el else ""

                        if not text:
                            continue

                        if not is_relevant(text, query):
                            seen.add(post_url)
                            continue

                        save_to_sheet({
                            "post_title": text[:80],
                            "post_text": text,
                            "location": location,
                            "post_datetime": post_datetime,
                            "profile_url": profile_url,
                            "website_url": website_url
                        })

                        seen.add(post_url)
                        print(f"Saved: @{username}")
                        time.sleep(random.uniform(1, 3))

                    except Exception as e:
                        print(f"Tweet parse error: {e}")
                        continue

            except Exception as e:
                print(f"Query error: {e}")
                continue

            time.sleep(random.uniform(3, 6))

        await browser.close()

    save_seen(seen)
    print("\nDone!")

asyncio.run(search_and_save())
