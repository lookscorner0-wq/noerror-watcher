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
    "n8n help"
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
    prompt = f"""You are Bilal, Sales Manager of a digital agency.

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

def save_to_sheet(post: dict, score: int):
    payload = {
        "A": time.strftime("%Y-%m-%d %H:%M"),
