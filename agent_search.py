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

def is_relevant(post_text: str) -> dict:
    prompt = f"""You are a lead qualifier for a digital agency.

COMPANY CONTEXT:
{COMPANY_MEMORY}

Analyze this Twitter post and decide if this person is a potential client.

Tweet: {post_text}

Reply in this exact format only:
relevant: yes
need: WhatsApp Automation
reason: One short sentence

OR

relevant: no
need: none
reason: One short sentence

NEED must be one of these only:
- WhatsApp Automation
- Email Automation
- AI Chatbot
- Lead Generation
- Social Media Marketing
- N8N Workflow
- Make.com Workflow
- Custom AI Agent
- Complex Automation
- General Automation

EXAMPLE LEADS (relevant: yes):

Tweet: Looking for someone to build a WhatsApp chatbot for my restaurant. DM me.
relevant: yes
need: WhatsApp Automation
reason: Business owner needs WhatsApp chatbot built

Tweet: Urgent hiring - need n8n automation expert for our e-commerce store
relevant: yes
need: N8N Workflow
reason: Hiring for specific automation tool we offer

Tweet: Anyone know a good agency for AI chatbot integration? Budget ready.
relevant: yes
need: AI Chatbot
reason: Asking for recommendation with budget ready

Tweet: We are wasting 3 hours daily on manual emails. Need automation help ASAP.
relevant: yes
need: Email Automation
reason: Clear pain point, wants solution urgently

EXAMPLE NON-LEADS (relevant: no):

Tweet: I build WhatsApp chatbots for businesses. DM to get started.
relevant: no
need: none
reason: Selling their own service, competitor

Tweet: n8n is amazing for automation workflows. Here is how I use it...
relevant: no
need: none
reason: Sharing tips, no buying intent

Tweet: ChatGPT vs Claude - which is better for coding?
relevant: no
need: none
reason: Opinion post, no personal need

SAY relevant: yes IF ANY OF THESE:
- Person is asking someone else to build, automate, or manage something for them
- Business owner or founder who needs a service built or automated
- Clear job post hiring for automation, AI, chatbot, social media, or lead gen role
- Person frustrated with manual work and wants to automate
- Person asking for recommendations for a developer or agency

SAY relevant: no IF ANY OF THESE:
- Person is selling or offering their own services
- Tweet contains: DM to get started, I offer, I help businesses, I build, my services, I create, I automate, my agency
- Person sharing their own project, portfolio, or case study
- Person looking for a full time job or internship
- General opinion or discussion about AI with no personal need
- Crypto, trading, or finance automation
- Big tech company hiring (Google, Microsoft, Meta, Binance)
- Complaining about someone else product with no buying intent
- Sharing tips, threads, or educational content"""

    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 80,
                "temperature": 0.3,
                "messages": [{"role": "user", "content": prompt}]
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
