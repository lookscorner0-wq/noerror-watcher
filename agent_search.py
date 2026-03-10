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

BUYING SIGNALS:
- "looking for", "need", "seeking", "want to hire", "required", "anyone know"
- "automation expert", "chatbot developer", "AI agent builder"
- "workflow automation", "n8n developer", "make.com expert"
- "whatsapp bot", "email automation", "social media help"
- "AI integration", "custom bot", "lead generation system"
- "deploy chatbot", "build automation", "AI assistant for my business"
- "DMs open", "taking clients", asking for recommendations

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
    "need chatbot",
    "hire ai developer",
    "automate my business",
    "need automation help",
    "looking for developer",
    "build me a bot",
    "ai chatbot for my",
    "whatsapp bot needed",
    "workflow help needed",
    "n8n help",
    "need ai automation expert",
    "looking for social media manager",
    "content marketer needed",
    "hiring lead generation expert",
    "need make.com developer",
    "looking for chatbot developer",
    "want to hire ai agent developer",
    "need workflow automation",
    "hiring automation specialist",
    "need n8n expert"
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def is_relevant(post_text: str) -> dict:
    prompt = f"""You are a strict lead qualifier for a digital agency.

COMPANY SERVICES:
{COMPANY_MEMORY}

Analyze this Twitter post. Answer relevant: yes ONLY if the person is clearly ASKING TO HIRE or BUY a service.

Post: {post_text}

Reply in this exact format only:
relevant: yes
score: 8
reason: One short sentence

OR

relevant: no
score: 2
reason: One short sentence

STRICT RULES - say relevant: no if any of these are true:
- Person is SELLING or OFFERING their own services
- Post contains "I offer", "I help", "I build", "DM to get started", "my services", "I create", "I automate"
- Person is complaining about a product or chatbot
- Person is sharing opinions, tips, or content about AI or automation
- Person is asking for a job or full time employment
- Post is a general discussion with no clear purchase intent
- Post uses hashtags like #AIAutomation #LegalTech to promote their own content
- Big company job listings (Google, Microsoft, Binance, etc)
- Person is sharing their own project, portfolio, or case study
- Post is about crypto, trading bots, or finance automation

ONLY say relevant: yes if:
- Person says need, looking for, want to hire, seeking, anyone know, required, we are hiring
- They are clearly asking someone else to build or automate something for them
- They have a business problem and want someone to solve it
- It is a job post hiring for automation, AI, chatbot, social media, or lead gen role"""

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

                        result = is_relevant(text)
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

        await browser.close()

    save_seen(seen)
    print(f"\nDone! Saved: {saved_count} leads")

print("Starting agent...")
asyncio.run(search_and_save())
