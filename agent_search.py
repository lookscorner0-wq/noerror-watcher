import asyncio
import json
import os
import random
import requests
import time
from datetime import datetime, timezone
from playwright.async_api import async_playwright

OPENAI_KEY = os.environ["OPENAI_KEY"]
SHEET_URL  = os.environ["SHEET_URL"]
AUTH_TOKEN = os.environ["TWITTER_AUTH_TOKEN"]
CT0        = os.environ["TWITTER_CT0"]
TWID       = os.environ["TWITTER_TWID"]
SEEN_FILE  = "seen_posts.json"

SYSTEM_PROMPT = """You are a senior sales expert with 10 years of experience qualifying leads for a digital agency. You have a sharp eye for spotting genuine buyers versus competitors and self-promoters.

COMPANY: Digital Agency | OWNER: Mujeeb | SALES MANAGER: Bilal | WHATSAPP: +923147191066

SERVICES: AI Automation (N8N, Make.com), Lead Generation, AI Chatbots (WhatsApp, Email, Caller), Social Media Marketing, Custom AI Agents, WhatsApp & Email Automation

SEARCH CONTEXT:
These tweets come from searches like: need chatbot developer, hire ai automation expert, whatsapp bot needed, need n8n developer, looking for chatbot developer, hiring lead generation expert, need ai agent developer, want to automate my business.

So most tweets will already be somewhat relevant — your job is to filter out competitors and non-buyers only.""" IDEAL CLIENT: Business owners, startups, companies wanting to automate work or hire automation/AI experts

BUYING SIGNALS: "looking for", "need", "seeking", "want to hire", "required", "anyone know", "hiring"

NOT A CLIENT: Competitors selling own services, big tech job listings, crypto/trading bots, job seekers, opinion posts, project showcases"""

SKIP_KEYWORDS = [
    "crypto", "trading", "blockchain", "forex", "nft",
    "i build", "i offer", "i help businesses", "i create", "i automate",
    "dm to get started", "my services", "my agency", "i provide",
    "this is what my bot does", "this is what the bot does",
    "here is how i", "follow me", "check out my",
    "i am selling", "buy my", "my tool", "my product"

SEARCH_QUERIES = [
    "need chatbot developer",
    "hire ai automation expert",
    "whatsapp bot needed",
    "need n8n developer",
    "looking for chatbot developer",
    "hiring lead generation expert",
    "need ai agent developer",
    "want to automate my business"
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return {}
        cutoff = time.time() - 259200
        return {url: ts for url, ts in data.items() if ts > cutoff}
    return {}

def save_seen(seen: dict):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f)

def quick_filter(text: str) -> bool:
    text_lower = text.lower()
    for word in SKIP_KEYWORDS:
        if word in text_lower:
            print(f"Pre-filter blocked: {word}")
            return False
    return True

def is_relevant(post_text: str) -> dict:
    user_prompt = f"""Analyze this tweet and decide if this person is a potential paying client.

Tweet: {post_text}

THINK STEP BY STEP:
Step 1: Is this person ASKING for help or OFFERING a service?
Step 2: Does this tweet show a real business problem?
Step 3: Are they willing to pay someone else to solve it?

POSITIVE EXAMPLES:
Tweet: Looking for someone to build a WhatsApp chatbot for my restaurant.
relevant: yes | need: WhatsApp Automation

Tweet: Urgent hiring - need n8n expert for our e-commerce store.
relevant: yes | need: N8N Workflow

NEGATIVE EXAMPLES:
Tweet: I build WhatsApp chatbots for businesses. DM to get started.
relevant: no | need: none

Tweet: This is what my bot does — customers can order on WhatsApp.
relevant: no | need: none

Reply in this exact format only:
relevant: yes
need: WhatsApp Automation
reason: One short sentence

OR

relevant: no
need: none
reason: One short sentence

NEED must be one of: WhatsApp Automation, Email Automation, AI Chatbot, Lead Generation, Social Media Marketing, N8N Workflow, Make.com Workflow, Custom AI Agent, Complex Automation, General Automation"""

    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 80,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            },
            timeout=15
        )
        answer = res.json()["choices"][0]["message"]["content"].strip().lower()
        print(f"LLM: {answer}")

        relevant = "relevant: yes" in answer
        client_need = "General Automation"
        for line in answer.split("\n"):
            if line.startswith("need:"):
                client_need = line.replace("need:", "").strip().title()
                break

        return {"relevant": relevant, "need": client_need}

    except Exception as e:
        print(f"LLM error: {e}")
        return {"relevant": False, "need": ""}

def save_to_sheet(post: dict):
    payload = {
        "A": time.strftime("%Y-%m-%d %H:%M"),
        "B": post.get("post_title", ""),
        "E": post.get("post_text", ""),
        "M": post.get("location", ""),
        "N": post.get("client_need", ""),
        "O": "In Waiting",
        "P": "",
        "Q": post.get("post_datetime", ""),
        "S": post.get("profile_url", ""),
        "W": post.get("website_url", "")
    }
    try:
        res = requests.post(SHEET_URL, json=payload, timeout=10)
        print(f"Sheet: {res.text} | {post.get('profile_url')}")
    except Exception as e:
        print(f"Sheet error: {e}")

async def search_and_save():
    print("Function started!")
    seen = load_seen()
    print(f"Seen posts: {len(seen)}")
    saved_count = 0

    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        print("Browser launched!")
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await context.add_cookies([
            {"name": "auth_token", "value": AUTH_TOKEN, "domain": ".x.com", "path": "/"},
            {"name": "ct0",        "value": CT0,        "domain": ".x.com", "path": "/"},
            {"name": "twid",       "value": TWID,       "domain": ".x.com", "path": "/"},
        ])

        page = await context.new_page()
        page.set_default_timeout(30000)

        for query in SEARCH_QUERIES:
            print(f"\nSearching: {query}")
            try:
                q = query.replace(" ", "+")
                try:
                    await page.goto(
                        f"https://x.com/search?q={q}&f=live",
                        timeout=20000,
                        wait_until="domcontentloaded"
                    )
                except Exception as e:
                    print(f"Page load failed: {e}")
                    continue

                await page.wait_for_timeout(8000)
                await page.evaluate("window.scrollBy(0, 500)")
                await page.wait_for_timeout(3000)

                tweets = await page.query_selector_all('article[data-testid="tweet"]')
                print(f"Tweets found: {len(tweets)}")

                for tweet in tweets:
                    try:
                        link_el = await tweet.query_selector('a[href*="/status/"]')
                        link = await link_el.get_attribute("href") if link_el else ""
                        post_url = f"https://x.com{link}" if link else ""
                        if not post_url or post_url in seen:
                            continue

                        text_el = await tweet.query_selector('[data-testid="tweetText"]')
                        text = await text_el.inner_text() if text_el else ""
                        if not text:
                            continue

                        time_el = await tweet.query_selector("time")
                        post_datetime = await time_el.get_attribute("datetime") if time_el else ""
                        if post_datetime:
                            tweet_time = datetime.fromisoformat(post_datetime.replace("Z", "+00:00"))
                            diff = datetime.now(timezone.utc) - tweet_time
                            if diff.total_seconds() > 86400:
                                print(f"Too old - skip")
                                seen[post_url] = time.time()
                                continue

                        if not quick_filter(text):
                            seen[post_url] = time.time()
                            continue

                        user_el = await tweet.query_selector('[data-testid="User-Name"]')
                        user_text = await user_el.inner_text() if user_el else ""
                        username = user_text.split("\n")[1] if "\n" in user_text else user_text
                        profile_url = f"https://x.com/{username.replace('@', '')}"

                        website_url = ""
                        try:
                            all_links = await tweet.query_selector_all("a[href]")
                            for link_tag in all_links:
                                href = await link_tag.get_attribute("href") or ""
                                if (
                                    href.startswith("http")
                                    and "x.com" not in href
                                    and "twitter.com" not in href
                                    and "t.co" not in href
                                ):
                                    website_url = href
                                    break
                        except Exception:
                            website_url = ""

                        loc_el = await tweet.query_selector('[data-testid="UserLocation"]')
                        location = await loc_el.inner_text() if loc_el else ""

                        result = is_relevant(text)
                        seen[post_url] = time.time()

                        if not result["relevant"]:
                            print(f"Not relevant - skip")
                            continue

                        save_to_sheet({
                            "post_title":    text[:80],
                            "post_text":     text,
                            "location":      location,
                            "post_datetime": post_datetime,
                            "profile_url":   profile_url,
                            "website_url":   website_url,
                            "client_need":   result["need"]
                        })

                        saved_count += 1
                        print(f"Saved: @{username} | Need: {result['need']}")
                        time.sleep(random.uniform(1, 3))

                    except Exception as e:
                        print(f"Tweet error: {e}")
                        continue

            except Exception as e:
                print(f"Query error: {e}")
                continue

            time.sleep(random.uniform(4, 8))

        await browser.close()

    save_seen(seen)
    print(f"\nDone! Saved: {saved_count} leads")

print("Starting agent...")
asyncio.run(search_and_save())
