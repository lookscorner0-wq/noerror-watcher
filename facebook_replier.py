import os
import asyncio
import random
import requests
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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36",
]

SYSTEM_PROMPT = """
You are a sales manager for NoErrors — an AI Automation Agency.
Your role is to continue conversations with potential clients on Facebook and convert them.

SERVICES WE OFFER:
1. Lead Generation (AI-powered outreach, Facebook automation, email campaigns, B2B database scraping)
2. Social Media Content Marketing (AI content calendar, auto-posting, LinkedIn/Instagram/Facebook/TikTok)
3. AI Chatbots and Agents (customer support bots, appointment bots, WhatsApp bots, website chatbots)
4. Custom Workflows (N8N, Make, Zapier, Pabbly automation setup and management)

CLIENT TYPES:
- Main Client: Small business, solo founder, startup — casual friendly tone, curiosity hooks, humor allowed, emojis allowed
- GoodClient: Growing company, SaaS, agency, mid-size — professional but warm, mirror their technical language
- Opportunity: Enterprise, Fortune, multinational — zero emojis, formal tone, push for discovery call always

HARD RULES:
1. NEVER share price in first or second message
2. NEVER sound salesy — always sound helpful and specific
3. NEVER use markdown, bold, bullets — plain text only
4. NEVER reveal you are an AI
5. NEVER promise delivery timeline before scoping
6. NEVER reveal team size
7. NEVER give price to Opportunity — push for discovery call
8. NEVER agree to free trial — offer free audit instead
9. NEVER compete on price — compete on value and ROI

CONVERSATION GOAL:
- Continue where watcher left off
- Understand their exact need
- Position solution with result number
- Push for WhatsApp or discovery call

SPECIAL CASES:
- If client says DM me / message me / inbox me:
  Reply: Sure, I am already here in your DMs! What would you like to discuss?
- If client says WhatsApp me / contact on WhatsApp:
  Reply: Happy to connect on WhatsApp! Could you share your number? I will reach out right away.
- If client asks for proof / results / case study:
  Reply: Absolutely, let me share what we delivered for a similar client.

OUTPUT:
- Plain text only
- Max 3 sentences per reply
- Never start with Hi or Hello
- Start with their point directly
"""

# ============================================================
# SUPABASE
# ============================================================
def supabase_get(table, params):
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            },
            params=params,
            timeout=10
        )
        return res.json()
    except:
        return []

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
        print(f"Supabase insert error: {e}")
        return False

def supabase_update(table, match_col, match_val, data):
    try:
        res = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type":  "application/json",
            },
            params={match_col: f"eq.{match_val}"},
            json=data,
            timeout=10
        )
        return res.status_code in [200, 204]
    except Exception as e:
        print(f"Supabase update error: {e}")
        return False

def get_conversation_history(profile_url):
    return supabase_get("conversations", {
        "profile_url": f"eq.{profile_url}",
        "platform":    "eq.facebook",
        "select":      "*",
        "order":       "created_at.desc",
        "limit":       "10"
    })

def is_already_replied(profile_url, message_type):
    rows = supabase_get("conversations", {
        "profile_url":  f"eq.{profile_url}",
        "platform":     "eq.facebook",
        "sender":       "eq.agent",
        "message_type": f"eq.{message_type}",
        "select":       "id"
    })
    return len(rows) > 0

def notify_manager(signal, profile_url, client_name, client_type, reply_text, their_message):
    supabase_insert("agent_signals", {
        "from_agent":  "facebook_replier",
        "to_agent":    "manager_agent",
        "signal_type": f"{signal.lower()}_alert",
        "payload":     str({
            "platform":     "facebook",
            "client_name":  client_name,
            "profile_url":  profile_url,
            "client_type":  client_type,
            "their_message": their_message,
            "our_reply":    reply_text,
            "signal":       signal
        }),
        "status": "pending"
    })
    print(f"  Manager notified — {signal} signal!")

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

def detect_signal(text):
    text = text.lower()
    if any(x in text for x in ["yes", "interested", "lets talk", "sounds good",
                                "how much", "tell me more", "great", "sure",
                                "okay", "proceed", "let us talk"]):
        return "Green"
    if any(x in text for x in ["no thanks", "not interested", "already hired",
                                "not looking", "pass", "no need"]):
        return "Red"
    if any(x in text for x in ["contract", "legal", "nda", "proof", "portfolio",
                                "past work", "references", "case study",
                                "have you done", "experience"]):
        return "Yellow"
    return None

def detect_whatsapp_request(text):
    return any(x in text.lower() for x in ["whatsapp", "whats app", "wa me",
                                             "contact on whatsapp", "whatsapp me"])

def detect_dm_request(text):
    return any(x in text.lower() for x in ["dm me", "message me", "inbox me",
                                             "send me a message", "private message",
                                             "direct message"])

def detect_proof_request(text):
    return any(x in text.lower() for x in ["proof", "results", "case study", "portfolio",
                                             "past work", "examples", "references",
                                             "have you done", "show me", "experience"])

def generate_reply(their_message, context, client_type):
    context_text = ""
    if context.get("dm_history"):
        context_text += "=== DM Conversation History ===\n"
        for msg in context["dm_history"]:
            context_text += f"{msg['role']}: {msg['text']}\n"
    if context.get("post_description"):
        context_text += f"\n=== Original Post ===\n{context['post_description']}\n"
    if context.get("our_comment"):
        context_text += f"\n=== Our First Comment ===\n{context['our_comment']}\n"

    temp = 0.3 if client_type == "Opportunity" else 0.5

    reply = call_openai([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": (
            f"{context_text}\n\n"
            f"Client just said: {their_message}\n"
            f"Client type: {client_type}\n\n"
            f"Write next reply. Max 3 sentences. Plain text only. "
            f"No price. Continue conversation naturally."
        )}
    ], max_tokens=120, temperature=temp)

    return reply.replace("**", "").replace("*", "").replace("#", "").replace("\n", " ")

# ============================================================
# HUMAN TYPING
# ============================================================
async def human_type(element, text):
    for char in text:
        await element.type(char, delay=random.randint(80, 160))
        if random.random() < 0.05:
            await asyncio.sleep(random.uniform(0.2, 0.5))

# ============================================================
# REPLY TO DM
# ============================================================
async def reply_to_dm(page, conv_url, reply_text):
    try:
        await page.goto(conv_url, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(4, 6))

        msg_box = await page.query_selector(
            'div[role="textbox"], div[contenteditable="true"]'
        )
        if not msg_box:
            print("  DM reply box not found")
            return False

        await page.evaluate("el => { el.click(); el.focus(); }", msg_box)
        await asyncio.sleep(1)
        await human_type(msg_box, reply_text)
        await asyncio.sleep(random.uniform(2, 3))

        send_btn = await page.query_selector('div[aria-label="Send"], div[aria-label="Press Enter to send"]')
        if send_btn:
            await send_btn.click()
        else:
            await msg_box.press("Enter")

        await asyncio.sleep(2)
        print("  DM reply sent!")
        return True

    except Exception as e:
        print(f"  DM reply error: {e}")
        return False

# ============================================================
# REPLY TO COMMENT
# ============================================================
async def reply_to_comment(page, reply_text):
    try:
        clicked = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('[aria-label="Leave a comment"], [aria-label="Comment"]');
                for (const btn of btns) { btn.click(); return true; }
                return false;
            }
        """)
        if not clicked:
            print("  Comment reply button not found")
            return False

        await asyncio.sleep(3)

        comment_box = await page.query_selector('div[contenteditable="true"][role="textbox"]')
        if not comment_box:
            comment_box = await page.query_selector('div[contenteditable="true"]')
        if not comment_box:
            print("  Comment reply box not found")
            return False

        await page.evaluate("el => el.focus()", comment_box)
        await asyncio.sleep(1)
        await human_type(comment_box, reply_text)
        await asyncio.sleep(2)
        await comment_box.press("Enter")
        await asyncio.sleep(3)
        print("  Comment reply posted!")
        return True

    except Exception as e:
        print(f"  Comment reply error: {e}")
        return False

# ============================================================
# PROCESS INBOX DMs
# ============================================================
async def process_inbox(page):
    print("\n--- Checking Inbox DMs ---")
    try:
        await page.goto("https://www.facebook.com/messages/t", wait_until="domcontentloaded")
        await asyncio.sleep(6)

        convs = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('div[role="listitem"]').forEach(el => {
                    try {
                        const unread = el.querySelector('div[data-visualcompletion="ignore-dynamic"]');
                        const link   = el.querySelector('a[href*="/messages/t/"]');
                        const name   = el.querySelector('span');
                        if (link && name) {
                            results.push({
                                url:  link.href,
                                name: name.innerText.trim()
                            });
                        }
                    } catch(e) {}
                });
                return results.slice(0, 10);
            }
        """)

        print(f"  Conversations found: {len(convs)}")

        for conv in convs:
            try:
                print(f"\n  Processing: {conv['name']}")

                await page.goto(conv['url'], wait_until="domcontentloaded")
                await asyncio.sleep(4)

                dm_history = await page.evaluate("""
                    () => {
                        const messages = [];
                        document.querySelectorAll('div[role="row"]').forEach(el => {
                            const text = el.innerText.trim();
                            if (text.length > 2) {
                                const isMine = el.querySelector('div[data-scope="sent_message"]');
                                messages.push({
                                    role: isMine ? "Agent" : "Client",
                                    text: text
                                });
                            }
                        });
                        return messages.slice(-10);
                    }
                """)

                if not dm_history:
                    continue

                last_client_msg = ""
                for msg in reversed(dm_history):
                    if msg["role"] == "Client":
                        last_client_msg = msg["text"]
                        break

                if not last_client_msg:
                    print("  No client message found — skip")
                    continue

                print(f"  Last msg: {last_client_msg[:60]}")

                profile_url = conv['url'].split("?")[0]

                history_rows = get_conversation_history(profile_url)
                client_type = (
                    history_rows[0].get("client_type", "Main Client")
                    if history_rows
                    else get_client_type(last_client_msg)
                )

                if detect_whatsapp_request(last_client_msg):
                    reply  = "Happy to connect on WhatsApp! Could you share your number? I will reach out right away."
                    signal = "Green"
                elif detect_dm_request(last_client_msg):
                    reply  = "Sure, I am already here in your DMs! What would you like to discuss?"
                    signal = "Green"
                else:
                    signal = detect_signal(last_client_msg)
                    if signal == "Red":
                        print("  Red signal — closing")
                        supabase_update("conversations", "profile_url", profile_url, {"status": "closed"})
                        continue

                    reply = generate_reply(
                        their_message=last_client_msg,
                        context={"dm_history": dm_history},
                        client_type=client_type
                    )

                success = await reply_to_dm(page, conv['url'], reply)

                if success:
                    supabase_insert("conversations", {
                        "platform":    "facebook",
                        "profile_url": profile_url,
                        "client_type": client_type,
                        "message":     last_client_msg,
                        "sender":      "client",
                        "message_type": "dm",
                        "status":      "conversation_started"
                    })
                    supabase_insert("conversations", {
                        "platform":    "facebook",
                        "profile_url": profile_url,
                        "client_type": client_type,
                        "message":     reply,
                        "sender":      "agent",
                        "message_type": "dm",
                        "status":      "conversation_started"
                    })
                    supabase_update("leads_queue", "potential_client_profile", profile_url,
                                   {"status": "warm" if signal == "Green" else "active"})
                    if signal in ["Green", "Yellow"]:
                        notify_manager(signal, profile_url, conv['name'], client_type, reply, last_client_msg)
                    supabase_insert("agent_logs", {
                        "agent_name": "facebook_replier",
                        "action":     f"DM replied to {conv['name']} | Signal: {signal}",
                        "details":    profile_url,
                        "status":     "success"
                    })

                await asyncio.sleep(random.uniform(15, 30))

            except Exception as e:
                print(f"  Conv error: {e}")
                continue

    except Exception as e:
        print(f"  Inbox error: {e}")

# ============================================================
# PROCESS NOTIFICATIONS
# ============================================================
async def process_notifications(page):
    print("\n--- Checking Notifications ---")
    try:
        await page.goto("https://www.facebook.com/notifications", wait_until="domcontentloaded")
        await asyncio.sleep(6)

        notifications = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('div[role="article"]').forEach(el => {
                    try {
                        const text = (el.innerText || "").toLowerCase();
                        if (!text.includes("comment") && !text.includes("replied")) return;
                        const links = el.querySelectorAll('a[href*="facebook.com"]');
                        let postUrl     = "";
                        let profileUrl  = "";
                        let authorName  = "";
                        for (const link of links) {
                            const href = link.href || "";
                            if (href.includes("/posts/") || href.includes("?v=") || href.includes("story_fbid")) {
                                postUrl = href.split("?")[0];
                            }
                            if (href.includes("/profile.php") || (href.includes("facebook.com/") && !href.includes("/posts") && !href.includes("/notifications"))) {
                                profileUrl = href.split("?")[0];
                                authorName = link.innerText.trim().split("\\n")[0];
                            }
                        }
                        if (postUrl || profileUrl) {
                            results.push({ postUrl, profileUrl, authorName, text: text.substring(0, 100) });
                        }
                    } catch(e) {}
                });
                return results.slice(0, 10);
            }
        """)

        print(f"  Notifications found: {len(notifications)}")

        for notif in notifications:
            try:
                profile_url = notif["profileUrl"]
                post_url    = notif["postUrl"]
                author_name = notif["authorName"]

                print(f"\n  From: {author_name}")

                if not post_url and not profile_url:
                    continue

                if is_already_replied(profile_url, "comment_reply"):
                    print("  Already replied — skip")
                    continue

                history_rows = supabase_get("conversations", {
                    "profile_url":  f"eq.{profile_url}",
                    "platform":     "eq.facebook",
                    "message_type": "eq.comment",
                    "select":       "*",
                    "limit":        "1"
                })
                client_type = history_rows[0].get("client_type", "Main Client") if history_rows else "Main Client"
                our_comment = history_rows[0].get("message", "") if history_rows else ""

                if post_url:
                    await page.goto(post_url, wait_until="domcontentloaded")
                    await asyncio.sleep(4)

                their_reply = await page.evaluate("""
                    () => {
                        const items = document.querySelectorAll('div[role="article"]');
                        for (const item of items) {
                            const text = item.innerText.trim();
                            if (text.length > 5) return text;
                        }
                        return "";
                    }
                """)

                if not their_reply:
                    print("  Could not find reply text — skip")
                    continue

                print(f"  Their reply: {their_reply[:60]}")
                signal = detect_signal(their_reply)

                if detect_whatsapp_request(their_reply):
                    reply_msg = "Happy to connect on WhatsApp! Could you drop your number here and I will reach out right away?"
                    signal    = "Green"
                elif detect_dm_request(their_reply):
                    reply_msg = "Sure, just sent you a message directly — check your inbox!"
                    signal    = "Green"
                elif signal == "Red":
                    print("  Red signal — closing")
                    supabase_update("conversations", "profile_url", profile_url, {"status": "closed"})
                    continue
                else:
                    reply_msg = generate_reply(
                        their_message=their_reply,
                        context={
                            "post_description": notif.get("text", ""),
                            "our_comment":      our_comment
                        },
                        client_type=client_type
                    )

                success = await reply_to_comment(page, reply_msg)

                if success:
                    supabase_insert("conversations", {
                        "platform":    "facebook",
                        "profile_url": profile_url,
                        "client_type": client_type,
                        "message":     their_reply,
                        "sender":      "client",
                        "message_type": "comment_reply",
                        "status":      "conversation_started"
                    })
                    supabase_insert("conversations", {
                        "platform":    "facebook",
                        "profile_url": profile_url,
                        "client_type": client_type,
                        "message":     reply_msg,
                        "sender":      "agent",
                        "message_type": "comment_reply",
                        "status":      "conversation_started"
                    })
                    supabase_update("conversations", "profile_url", profile_url, {"status": "conversation_started"})
                    if signal in ["Green", "Yellow"]:
                        notify_manager(signal, profile_url, author_name, client_type, reply_msg, their_reply)
                    supabase_insert("agent_logs", {
                        "agent_name": "facebook_replier",
                        "action":     f"Comment replied to {author_name} | Signal: {signal}",
                        "details":    profile_url,
                        "status":     "success"
                    })

                await asyncio.sleep(random.uniform(15, 25))

            except Exception as e:
                print(f"  Notification error: {e}")
                continue

    except Exception as e:
        print(f"  Notifications error: {e}")

# ============================================================
# MAIN
# ============================================================
async def run_replier():
    print(f"\n{'='*50}")
    print(f"Facebook Replier Started")
    print(f"{'='*50}\n")

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

        await process_inbox(page)
        await process_notifications(page)

        print(f"\n{'='*50}")
        print(f"Facebook Replier Done!")
        print(f"{'='*50}")
        await browser.close()

await run_replier()
