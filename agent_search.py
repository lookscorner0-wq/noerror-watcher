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
SALES MANAGER: Bilal
PHONE / WHATSAPP: +923147191066

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

BUYING SIGNALS:
- "looking for", "need", "seeking", "want to hire", "required", "anyone know"
- "automation expert", "chatbot developer", "AI agent builder"
- "workflow automation", "n8n developer", "make.com expert"
- "whatsapp bot", "email automation", "social media help"
- "AI integration", "custom bot", "lead generation system"
- "deploy chatbot", "build automation", "AI assistant for my business"
- Anyone hiring for automation, AI, chatbot, or social media roles

NOT A CLIENT:
- People promoting or selling their OWN services (competitors)
- Big company job listings (Google, Microsoft, Binance, etc)
- People discussing AI news, opinions, or trends with no buying intent
- Crypto or trading bot requests
- People looking for full time employment
- Random automation discussions with no clear buying intent
- People sharing their own projects or portfolios
"""

SEARCH_QUERIES = [
    "need chatbot developer",
    "hire ai developer",
    "looking for automation expert",
    "need n8n developer",
    "looking for make.com expert",
    "whatsapp bot needed",
    "build me a chatbot",
    "need ai agent developer",
    "hiring automation specialist",
    "need workflow automation help",
    "looking for social media manager",
    "content marketer needed",
    "hiring lead generation expert",
    "need ai integration help",
    "want to automate my business",
    "looking for chatbot developer",
    "need whatsapp automation",
    "hire email automation expert",
    "need custom ai bot",
    "looking for ai assistant developer"
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def is_relevant(post_text: str, bio: str) -> dict:
     prompt = f"""You are a strict but fair lead qualifier for a digital agency.

COMPANY CONTEXT:
{COMPANY_MEMORY}

Analyze this Twitter post AND the user's profile bio together.

Tweet: {post_text}
Profile Bio: {bio if bio else "No bio available"}

Reply in this exact format only:
relevant: yes
score: 8
reason: One short sentence

OR

relevant: no
score: 2
reason: One short sentence

SAY relevant: yes IF ANY OF THESE:
- Person is asking someone else to build, automate, or manage something for them
- Founder or business owner who needs a service built or automated
- Person has a business problem and wants someone to solve it
- Job post hiring for automation, AI, chatbot, social media, or lead gen role
- Bio is neutral and tweet has clear buying intent — give benefit of doubt
- Score is 7 or above

SAY relevant: no IF ANY OF THESE:
- Bio contains: "I build chatbots", "I offer services", "freelancer for hire", "automation agency", "I help businesses", "I provide"
- Founder alone is NOT a reason to reject — founders are often our best clients
- Building their own product is NOT a reason to reject unless they are selling dev services
- Tweet contains: "DM to get started", "I offer", "I help", "I build", "my services", "I create", "I automate"
- Person is sharing their own project, portfolio, or case study
- Person is looking for a full time job
- Pure opinion, tips, or news discussion about AI
- Crypto, trading, or finance bots
- Big tech company hiring (Google, Microsoft, Meta, Binance)
- Any doubt about buying intent = say no"""

  try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 60,
                "temperature": 0.3,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=15
        )
        answer = res.json()["choices"][0]["message"]["content"].strip().lower()
        print(f"LLM: {answer}")

        score = 5
        for line in answer.split("\n"):
            if line.startswith("score:"):
                try:
                    score = int(line.replace("score:", "").strip())
                except:
                    pass

        relevant = "relevant: yes" in answer and score >= 7

        return {"relevant": relevant, "score": score}

    except Exception as e:
        print(f"LLM error: {e}")
        return {"relevant": False, "score": 0}

async def get_profile_bio(page, username: str) -> str:
    try:
        profile_url = f"https://x.com/{username.replace('@', '')}"
        await page.goto(profile_url, timeout=15000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        bio_el = await page.query_selector('[data-testid="UserDescription"]')
        bio = await bio_el.inner_text() if bio_el else ""
        return bio.strip()
    except Exception:
        return ""

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

        search_page = await context.new_page()
        profile_page = await context.new_page()
        search_page.set_default_timeout(30000)
        profile_page.set_default_timeout(15000)

        for query in SEARCH_QUERIES:
            print(f"\nSearching: {query}")
            try:
                q = query.replace(" ", "+")
                try:
                    await search_page.goto(
                        f"https://x.com/search?q={q}&f=live",
                        timeout=20000,
                        wait_until="domcontentloaded"
                    )
                except Exception as e:
                    print(f"Page load failed: {e}")
                    continue

                await search_page.wait_for_timeout(8000)
                await search_page.evaluate("window.scrollBy(0, 500)")
                await search_page.wait_for_timeout(3000)

                tweets = await search_page.query_selector_all('article[data-testid="tweet"]')
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
                            if diff.total_seconds() > 604800:
                                print(f"Too old - skip")
                                seen.add(post_url)
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

                        bio = await get_profile_bio(profile_page, username)
                        print(f"Bio: {bio[:80] if bio else 'No bio'}")

                        result = is_relevant(text, bio)
                        seen.add(post_url)

                        if not result["relevant"]:
                            print(f"Not relevant - skip")
                            continue

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

        await search_page.close()
        await profile_page.close()
        await browser.close()

    save_seen(seen)
    print(f"\nDone! Saved: {saved_count} leads")

print("Starting agent...")
asyncio.run(search_and_save())
