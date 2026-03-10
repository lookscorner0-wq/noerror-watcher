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

COMPANY_MEMORY = """
COMPANY: Digital Agency
OWNER: Mujeeb
contact: +923147191066
SALES MANAGER: You (Bilal)

SERVICES:
- AI Automation Workflows (N8N, Make.com)
- Lead Generation Systems
- AI Chatbots (Customer Care, Booking, Email, WhatsApp, Caller Bots)
- Social Media Marketing and Content Marketing
- Complex Workflow Automation
- Personalized Assistant Bots
- Custom AI Agents
- WhatsApp and Email Automation

IDEAL CLIENT:
- Business owners wanting to automate repetitive work
- Startups needing chatbot or AI integration
- Companies looking to hire automation or AI experts
- Businesses needing WhatsApp, Email, or Social Media automation
- Anyone wanting to reduce manual work using AI
- Companies needing N8N or Make.com workflows
- Anyone needing custom AI agent or bot development

BUYING SIGNALS — these people are potential clients:
- "looking for", "need", "seeking", "want to hire", "required", "anyone know"
- "automation expert", "chatbot developer", "AI agent builder"
- "workflow automation", "n8n developer", "make.com expert"
- "whatsapp bot", "email automation", "social media help"
- "AI integration", "custom bot", "lead generation system"
- "deploy chatbot", "build automation", "AI assistant for my business"
- "DMs open", "taking clients", asking for recommendations

NOT A CLIENT — ignore these:
- People promoting or selling their OWN services (competitors)
- Big company job listings (Google, Microsoft, Binance, etc)
- People discussing AI news, opinions, or trends with no buying intent
- Crypto or trading bot requests
- People looking for full time employment
- Random automation discussions with no clear buying intent
- People sharing their own projects or portfolios
"""

# ============================================================
# LLM FILTER — Sales Manager decides relevance
# ============================================================
def is_relevant(post_text: str) -> dict:
    prompt = f"""You are Alex, Sales Manager of a digital agency.

COMPANY CONTEXT:
{COMPANY_MEMORY}

Analyze this Twitter post and decide if this person needs our services.

Post: {post_text}

Reply ONLY in this exact format — plain text, no JSON, no formatting:
relevant: yes
score: 8
reason: One short sentence explaining why

OR

relevant: no
score: 2
reason: One short sentence explaining why not

Rules:
- relevant: yes ONLY if they are actively looking to BUY or HIRE
- score 1-10 (10 = perfect client, 1 = completely irrelevant)
- Be strict — only say yes if there is clear buying intent
- Never say yes to competitors, job seekers, or opinion posts"""

    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 60,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=15
        )
        answer = res.json()["choices"][0]["message"]["content"].strip().lower()
        print(f"LLM: {answer}")

        relevant = "relevant: yes" in answer
        score = 5
        for line in answer.split("\n"):
            if line.startswith("score:"):
                try:
                    score = int(line.replace("score:", "").strip())
                except:
                    pass

        return {"relevant": relevant, "score": score}

    except Exception as e:
        print(f"LLM error: {e}")
        return {"relevant": False, "score": 0}

# ============================================================
# SHEET SAVE
# ============================================================
def save_to_sheet(post: dict, score: int):
    payload = {
        "A": time.strftime("%Y-%m-%d %H:%M"),
        "B": post.get("post_title", ""),
        "E": post.get("post_text", ""),
        "M": post.get("location", ""),
        "N": score,
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

# ============================================================
# SEEN POSTS
# ============================================================
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

# ============================================================
# SEARCH QUERIES — LLM generates from buying signals
# ============================================================
SEARCH_QUERIES = [
    "looking for chatbot developer",
    "need ai automation expert",
    "seeking workflow automation help",
    "want to hire ai agent developer",
    "need whatsapp automation",
    "looking for n8n developer",
    "need social media automation",
    "seeking make.com expert",
    "want to build ai chatbot",
    "need automation for my business"
]

# ============================================================
# MAIN SEARCH
# ============================================================
async def search_and_save():
    print("Function started!")
    seen = load_seen()
    print(f"Seen posts: {len(seen)}")
    saved_count = 0

    async with async_playwright() as p:
        print("Launching browser...")
        browser = await asyncio.wait_for(
    p.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox', 
            '--disable-dev-shm-usage',
            '--disable-gpu'
        ]
    ),
    timeout=60
)
        context = await browser.new_context()
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
                await page.goto(
                    f"https://x.com/search?q={q}&f=live",
                    timeout=30000
                )
                await page.wait_for_timeout(8000)
                await page.evaluate("window.scrollBy(0, 500)")
                await page.wait_for_timeout(3000)

                tweets = await page.query_selector_all('article[data-testid="tweet"]')
                print(f"Tweets found: {len(tweets)}")

                for tweet in tweets:
                    try:
                        # Post URL
                        link_el = await tweet.query_selector('a[href*="/status/"]')
                        link = await link_el.get_attribute("href") if link_el else ""
                        post_url = f"https://x.com{link}" if link else ""
                        if not post_url or post_url in seen:
                            continue

                        # Post text
                        text_el = await tweet.query_selector('[data-testid="tweetText"]')
                        text = await text_el.inner_text() if text_el else ""
                        if not text:
                            continue

                        # Age filter — max 48 hours
                        time_el = await tweet.query_selector("time")
                        post_datetime = await time_el.get_attribute("datetime") if time_el else ""
                        if post_datetime:
                            tweet_time = datetime.fromisoformat(post_datetime.replace("Z", "+00:00"))
                            diff = datetime.now(timezone.utc) - tweet_time
                            if diff.total_seconds() > 172800:
                                print(f"Too old — skip")
                                seen.add(post_url)
                                continue

                        # Username + profile
                        user_el = await tweet.query_selector('[data-testid="User-Name"]')
                        user_text = await user_el.inner_text() if user_el else ""
                        username = user_text.split("\n")[1] if "\n" in user_text else user_text
                        profile_url = f"https://x.com/{username.replace('@', '')}"

                        # External link
                        ext_el = await tweet.query_selector(
                            'a[href*="http"]:not([href*="x.com"]):not([href*="twitter.com"])'
                        )
                        website_url = await ext_el.get_attribute("href") if ext_el else ""

                        # Location
                        loc_el = await tweet.query_selector('[data-testid="UserLocation"]')
                        location = await loc_el.inner_text() if loc_el else ""

                        # LLM filter
                        result = is_relevant(text)
                        seen.add(post_url)

                        if not result["relevant"]:
                            print(f"Not relevant — skip")
                            continue

                        # Save to sheet
                        save_to_sheet({
                            "post_title":    text[:80],
                            "post_text":     text,
                            "location":      location,
                            "post_datetime": post_datetime,
                            "profile_url":   profile_url,
                            "website_url":   website_url
                        }, score=result["score"])

                        saved_count += 1
                        print(f"Saved: @{username} | Score: {result['score']}")
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
