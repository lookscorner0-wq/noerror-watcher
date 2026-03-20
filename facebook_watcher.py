import os
import asyncio
import random
import requests
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright

OPENAI_KEY   = os.environ.get("OPENAI_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

COOKIES = [
    {"name": "datr",     "value": os.environ.get("FB_DATR", ""),     "domain": ".facebook.com", "path": "/"},
    {"name": "sb",       "value": os.environ.get("FB_SB", ""),       "domain": ".facebook.com", "path": "/"},
    {"name": "c_user",   "value": os.environ.get("FB_C_USER", ""),   "domain": ".facebook.com", "path": "/"},
    {"name": "xs",       "value": os.environ.get("FB_XS", ""),       "domain": ".facebook.com", "path": "/"},
    {"name": "fr",       "value": os.environ.get("FB_FR", ""),       "domain": ".facebook.com", "path": "/"},
    {"name": "locale",   "value": "en_US",                           "domain": ".facebook.com", "path": "/"},
    {"name": "wd",       "value": os.environ.get("FB_WD", ""),       "domain": ".facebook.com", "path": "/"},
    {"name": "presence", "value": os.environ.get("FB_PRESENCE", ""), "domain": ".facebook.com", "path": "/"},
]

MAX_ACTIONS_PER_RUN = 5

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36",
]

SYSTEM_PROMPT = """
You are a sales manager for NoErrors — an AI Automation Agency.
Your role is to find potential clients on Facebook who need our services and convert them through smart, human, non-salesy conversation.

SERVICES WE OFFER:
1. Lead Generation (AI-powered outreach, Facebook automation, email campaigns, B2B database scraping)
2. Social Media Content Marketing (AI content calendar, auto-posting, LinkedIn/Instagram/Facebook/TikTok)
3. AI Chatbots and Agents (customer support bots, appointment bots, WhatsApp bots, website chatbots)
4. Custom Workflows (N8N, Make, Zapier, Pabbly automation setup and management)

CLIENT TYPES:
- Main Client: Small business, solo founder, startup — casual friendly tone, curiosity hooks, humor allowed, emojis allowed
- GoodClient: Growing company, SaaS, agency, mid-size — professional but warm, mirror their technical language, free audit offer works well
- Opportunity: Enterprise, Fortune, multinational, large corporation — zero emojis, formal tone, lead with credibility and case study, push for discovery call always

HARD RULES:
1. NEVER share price in first or second message
2. NEVER sound salesy — always sound helpful and specific
3. NEVER use markdown, bold, bullets, or formatting — plain text only
4. NEVER reveal you are an AI
5. NEVER mention services client did not ask for in first message
6. NEVER send more than 180 characters in first outreach
7. NEVER use emojis with Opportunity clients

WHAT WORKS:
1. Mirror exact technical language from their post
2. Frame hook around what client is LOSING not what we offer
3. Include specific result number when possible
4. For Main Client — curiosity question hook, casual tone
5. For GoodClient — lead with free audit offer
6. For Opportunity — open with enterprise reference and specific result
7. Never start with Hi I am from NoErrors — start with their pain point

OUTPUT FORMAT FOR COMMENTS:
- Plain text only
- Maximum 180 characters
- No hashtags
- End with soft question

OUTPUT FORMAT FOR DMs:
- Plain text only
- Maximum 2 sentences
- Start with their pain point
"""

KEYWORDS_POOL = [
    "need chatbot developer",
    "need AI automation",
    "looking for social media manager",
    "need lead generation",
    "looking for workflow automation",
    "need customer support bot",
    "need AI agent developer",
    "need CRM automation",
    "need social media automation",
    "hiring AI developer",
    "need digital marketing automation",
    "looking for chatbot",
]

# ============================================================
# SUPABASE
# ============================================================
def supabase_insert(table, data):
    try:
        res = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type":  "application/json",
                "Prefer":        "return=minimal"
            },
            json=data,
            timeout=10
        )
        return res.status_code in [200, 201]
    except Exception as e:
        print(f"Supabase error: {e}")
        return False

def is_already_contacted(profile_url):
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/conversations",
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "profile_url": f"eq.{profile_url}",
                "platform":    "eq.facebook",
                "select":      "conv_id"
            },
            timeout=10
        )
        return len(res.json()) > 0
    except:
        return False

# ============================================================
# URL CLEANER
# ============================================================
def clean_url(url):
    if not url:
        return ""
    parsed = urlparse(url)
    if "profile.php" in url:
        params = parse_qs(parsed.query)
        uid = params.get("id", [""])[0]
        return f"https://www.facebook.com/profile.php?id={uid}"
    return f"https://www.facebook.com{parsed.path}"

# ============================================================
# OPENAI
# ============================================================
def call_openai(messages, max_tokens=150, temperature=0.5):
    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={
                "model":       "gpt-4o-mini",
                "messages":    messages,
                "max_tokens":  max_tokens,
                "temperature": temperature
            },
            timeout=30
        )
        return res.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"OpenAI error: {e}")
        return ""

def get_client_type(text):
    text = text.lower()
    if any(x in text for x in ["enterprise", "fortune", "global", "multinational", "corporate"]):
        return "Opportunity"
    if any(x in text for x in ["startup", "saas", "growing", "series a", "scale up", "agency"]):
        return "GoodClient"
    return "Main Client"

def is_relevant(post_text):
    result = call_openai([
        {"role": "system", "content": (
            "You are a lead qualifier for NoErrors — an AI Automation Agency. "
            "Reply ONLY: relevant: yes OR relevant: no. "
            "relevant: yes if the person is LOOKING FOR or NEEDS someone to build "
            "chatbot, AI agent, automation, lead gen, social media service, CRM, or workflow. "
            "relevant: no if it is a tutorial, self-promotion, news, job posting, or unrelated content."
        )},
        {"role": "user", "content": f"Post: {post_text[:300]}"}
    ], max_tokens=10, temperature=0.1)
    return "relevant: yes" in result.lower()

def generate_dm(post_text, client_type):
    temp = 0.3 if client_type == "Opportunity" else 0.5
    dm = call_openai([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Write a Facebook DM. Client type: {client_type}.\n"
            f"Post: {post_text[:300]}\n"
            f"Max 2 sentences. Plain text. Start with their pain point. No price."
        )}
    ], max_tokens=100, temperature=temp)
    return dm.replace("**", "").replace("*", "").replace("#", "").replace("\n", " ")

def generate_comment(post_text, client_type):
    temp = 0.7 if client_type == "Main Client" else 0.4
    comment = call_openai([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Write a Facebook comment. Client type: {client_type}.\n"
            f"Post: {post_text[:300]}\n"
            f"Max 180 chars. Plain text. End with soft question. No hashtags."
        )}
    ], max_tokens=80, temperature=temp)
    return comment.replace("**", "").replace("*", "").replace("#", "").replace("\n", " ")[:180]

# ============================================================
# KEYWORDS
# ============================================================
def generate_keywords():
    keywords = random.sample(KEYWORDS_POOL, 4)
    print(f"Keywords this run: {keywords}")
    return keywords

# ============================================================
# SCRAPER
# ============================================================
EXTRACT_JS = """
    () => {
        const results = [];
        document.querySelectorAll('[aria-posinset]').forEach(el => {
            try {
                const textEl = el.querySelector('[data-ad-rendering-role="story_message"]');
                const text = textEl ? textEl.innerText.trim() : "";
                if (text.length < 30) return;
                let authorName = "";
                let authorUrl  = "";
                const links = el.querySelectorAll('h2 a, h3 a, strong a, a[role="link"]');
                for (const link of links) {
                    const href = link.href || "";
                    const name = link.innerText.trim().split("\\n")[0];
                    if (
                        name.length > 1 &&
                        !href.includes("/search") &&
                        !href.includes("l.facebook") &&
                        !href.includes("/photo") &&
                        !href.includes("/video") &&
                        !href.includes("/posts")
                    ) {
                        authorName = name;
                        authorUrl  = href;
                        break;
                    }
                }
                const posIndex = el.getAttribute("aria-posinset");
                results.push({ posIndex, text, authorName, authorUrl });
            } catch(e) {}
        });
        return results;
    }
"""

async def scrape_posts(page, keyword):
    url = f"https://www.facebook.com/search/posts/?q={keyword.replace(' ', '%20')}"
    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(6)
    all_posts = {}
    for i in range(6):
        batch = await page.evaluate(EXTRACT_JS)
        for item in batch:
            all_posts[item["posIndex"]] = item
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(2.5)
    print(f"  Posts scraped: {len(all_posts)}")
    return list(all_posts.values())

# ============================================================
# DM
# ============================================================
async def send_dm(page, profile_url, message):
    try:
        await page.goto(profile_url, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        msg_btn = await page.query_selector('div[aria-label="Message"], a[aria-label="Message"]')
        if not msg_btn:
            msg_btn = await page.query_selector('div[role="button"]:has-text("Message")')
        if not msg_btn:
            print("  DM button not found")
            return False
        await page.evaluate("el => el.click()", msg_btn)
        await asyncio.sleep(3)
        msg_box = await page.query_selector('div[role="textbox"], div[contenteditable="true"]')
        if not msg_box:
            print("  DM box not found")
            return False
        await page.evaluate("el => { el.click(); el.focus(); }", msg_box)
        await asyncio.sleep(1)
        for char in message:
            await msg_box.type(char, delay=random.randint(50, 100))
        await asyncio.sleep(2)
        send_btn = await page.query_selector('div[aria-label="Send"], div[aria-label="Press Enter to send"]')
        if send_btn:
            await send_btn.click()
        else:
            await msg_box.press("Enter")
        await asyncio.sleep(2)
        print("  DM sent!")
        return True
    except Exception as e:
        print(f"  DM error: {e}")
        return False

# ============================================================
# COMMENT
# ============================================================
async def post_comment(page, comment_text):
    try:
        clicked = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('[aria-label="Leave a comment"], [aria-label="Comment"]');
                for (const btn of btns) { btn.click(); return true; }
                return false;
            }
        """)
        if not clicked:
            print("  Comment button not found")
            return False
        await asyncio.sleep(3)
        comment_box = await page.query_selector('div[contenteditable="true"][role="textbox"]')
        if not comment_box:
            comment_box = await page.query_selector('div[contenteditable="true"]')
        if not comment_box:
            print("  Comment box not found")
            return False
        await page.evaluate("el => el.focus()", comment_box)
        await asyncio.sleep(1)
        for char in comment_text:
            await comment_box.type(char, delay=random.randint(50, 100))
        await asyncio.sleep(2)
        await comment_box.press("Enter")
        await asyncio.sleep(3)
        print("  Comment posted!")
        return True
    except Exception as e:
        print(f"  Comment error: {e}")
        return False

# ============================================================
# MAIN
# ============================================================
async def run_watcher():
    print(f"\n{'='*50}")
    print(f"Facebook Watcher Started")
    print(f"{'='*50}\n")

    keywords     = generate_keywords()
    actions_done = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768}
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        await context.add_cookies(COOKIES)
        page = await context.new_page()

        await page.goto("https://www.facebook.com", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        if "login" in page.url:
            print("Session expired — refresh cookies!")
            await browser.close()
            return

        print("Session valid!\n")

        for keyword in keywords:
            if actions_done >= MAX_ACTIONS_PER_RUN:
                break

            print(f"\nSearching: '{keyword}'")
            posts = await scrape_posts(page, keyword)

            for post in posts:
                if actions_done >= MAX_ACTIONS_PER_RUN:
                    break

                post_text   = post["text"]
                author_name = post["authorName"]
                author_url  = clean_url(post["authorUrl"])

                if not author_url:
                    continue

                if is_already_contacted(author_url):
                    print(f"  Already contacted — skip")
                    continue

                if not is_relevant(post_text):
                    print(f"  Not relevant — skip")
                    continue

                client_type = get_client_type(post_text)
                print(f"  Relevant! {author_name} | {client_type}")

                dm_text  = generate_dm(post_text, client_type)
                print(f"  Trying DM: {dm_text[:80]}...")

                success  = await send_dm(page, author_url, dm_text)
                msg_type = "dm"
                message  = dm_text

                if not success:
                    print("  DM failed — trying comment...")
                    await page.goto(
                        f"https://www.facebook.com/search/posts/?q={keyword.replace(' ', '%20')}",
                        wait_until="domcontentloaded"
                    )
                    await asyncio.sleep(5)
                    comment_text = generate_comment(post_text, client_type)
                    print(f"  Comment: {comment_text[:80]}...")
                    success  = await post_comment(page, comment_text)
                    msg_type = "comment"
                    message  = comment_text

                status = "success" if success else "failed"

                if success:
                    supabase_insert("leads_queue", {
                        "platform":                 "facebook",
                        "potential_client_name":    author_name,
                        "potential_client_profile": author_url,
                        "post_content":             post_text[:500],
                        "post_url":                 f"https://www.facebook.com/search/posts/?q={keyword.replace(' ', '%20')}",
                        "assigned_to":              "facebook_watcher",
                        "status":                   "contacted"
                    })
                    supabase_insert("conversations", {
                        "platform":    "facebook",
                        "profile_url": author_url,
                        "client_type": client_type,
                        "message":     message,
                        "sender":      "agent",
                        "message_type": msg_type,
                        "status":      "contacted"
                    })
                    supabase_insert("agent_logs", {
                        "agent_name": "facebook_watcher",
                        "action":     f"{'DM' if msg_type == 'dm' else 'Comment'} to {author_name}",
                        "details":    author_url,
                        "status":     status
                    })

                    actions_done += 1
                    print(f"  Logged to Supabase! {actions_done}/{MAX_ACTIONS_PER_RUN}")
                    await asyncio.sleep(random.uniform(8, 12))

        print(f"\n{'='*50}")
        print(f"Facebook Watcher Done! Actions: {actions_done}")
        print(f"{'='*50}")
        await browser.close()

await run_watcher()
