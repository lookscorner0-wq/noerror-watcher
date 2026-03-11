import os
import json
import time
import random
import re
import requests
from datetime import datetime

LI_AT         = os.environ["LI_AT"]
LI_JSESSIONID = os.environ["LI_JSESSIONID"]
OPENAI_KEY    = os.environ["OPENAI_KEY"]
SHEET_URL     = os.environ["SHEET_URL"]
SEEN_FILE     = "seen_urls.json"

SYSTEM_PROMPT = (
    "You are a senior sales expert with 10 years of experience qualifying leads for a digital agency. "
    "You have a sharp eye for spotting genuine buyers versus competitors and self-promoters.\n\n"
    "COMPANY: Digital Agency | OWNER: Mujeeb | SALES MANAGER: Bilal | WHATSAPP: +923147191066\n\n"
    "SERVICES: AI Automation (N8N, Make.com), Lead Generation, AI Chatbots (WhatsApp, Email, Caller), "
    "Social Media Marketing, Custom AI Agents, WhatsApp and Email Automation\n\n"
    "IDEAL CLIENT: Business owners, startups, companies wanting to automate work or hire automation/AI experts\n\n"
    "NOT A CLIENT: Full time job seekers, big tech companies, crypto/trading, opinion posts\n\n"
    "TASK: Analyze this job post or LinkedIn post and decide if this is a potential client.\n\n"
    "THINK STEP BY STEP:\n"
    "Step 1: Is this a Contract/Freelance job or a buying intent post?\n"
    "Step 2: Does it match our services?\n"
    "Step 3: Is the budget/intent clear?\n\n"
    "POSITIVE EXAMPLES:\n"
    "Title: Need AI Automation Expert — Contract\n"
    "relevant: yes | need: General Automation\n\n"
    "Title: Looking for Chatbot Developer — Freelance Project\n"
    "relevant: yes | need: AI Chatbot\n\n"
    "NEGATIVE EXAMPLES:\n"
    "Title: Senior Software Engineer — Full Time — Google\n"
    "relevant: no | need: none\n\n"
    "Title: We are hiring ML Engineer permanently\n"
    "relevant: no | need: none\n\n"
    "OUTPUT FORMAT:\n"
    "relevant: yes\n"
    "need: AI Chatbot\n"
    "reason: One short sentence\n\n"
    "OR\n\n"
    "relevant: no\n"
    "need: none\n"
    "reason: One short sentence\n\n"
    "NEED must be one of: WhatsApp Automation, Email Automation, AI Chatbot, Lead Generation, "
    "Social Media Marketing, N8N Workflow, Make.com Workflow, Custom AI Agent, Complex Automation, General Automation"
)

JOB_QUERIES = [
    "AI Automation Expert",
    "Chatbot Developer",
    "Social Media Marketing Manager",
    "Lead Generation Expert",
    "N8N Developer",
    "Make.com Expert",
    "WhatsApp Bot Developer",
    "Workflow Automation Expert"
]

POST_QUERIES = [
    "need ai automation",
    "looking for chatbot",
    "need social media manager",
    "automate my business",
    "need content creator",
    "whatsapp bot needed",
    "need lead generation"
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return {}
        cutoff = time.time() - 172800
        return {url: ts for url, ts in data.items() if ts > cutoff}
    return {}

def save_seen(seen: dict):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f)

def get_session():
    s = requests.Session()
    s.headers.update({
        "accept": "application/vnd.linkedin.normalized+json+2.1",
        "csrf-token": LI_JSESSIONID,
        "referer": "https://www.linkedin.com/jobs/search/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-li-lang": "en_US",
        "x-restli-protocol-version": "2.0.0",
        "cookie": f'JSESSIONID="{LI_JSESSIONID}"; li_at={LI_AT}'
    })
    return s

def is_relevant(title: str, description: str) -> dict:
    user_prompt = f"Title: {title}\nDescription: {description[:300]}"
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

def save_to_sheet(data: dict):
    try:
        res = requests.post(SHEET_URL, json=data, timeout=10)
        print(f"Sheet: {res.text}")
    except Exception as e:
        print(f"Sheet error: {e}")

def search_jobs(query: str, s: requests.Session) -> list:
    try:
        kw  = query.replace(" ", "%20")
        url = "https://www.linkedin.com/voyager/api/voyagerJobsDashJobCards"
        url += "?decorationId=com.linkedin.voyager.dash.deco.jobs.search.JobSearchCardsCollectionLite-88"
        url += "&count=10&q=jobSearch"
        url += f"&query=(origin:JOBS_HOME_SEARCH_BUTTON,keywords:{kw},locationUnion:(geoId:92000000),spellCorrectionEnabled:true)"
        url += "&servedEventEnabled=false&start=0&f_TPR=r172800&f_JT=C,F"
        res  = s.get(url, timeout=15)
        print(f"Jobs search '{query}': {res.status_code}")
        data  = res.json()
        cards = data.get("data", {}).get("metadata", {}).get("jobCardPrefetchQueries", [])
        ids   = []
        for card in cards:
            for key in card.get("prefetchJobPostingCard", {}).keys():
                match = re.search(r'\((\d+),', key)
                if match:
                    ids.append(match.group(1))
        print(f"Job IDs found: {ids}")
        return ids
    except Exception as e:
        print(f"Jobs search error: {e}")
        return []

def get_job_data(job_id: str, s: requests.Session) -> dict:
    try:
        time.sleep(random.uniform(2, 4))
        res = s.get(
            f"https://www.linkedin.com/voyager/api/jobs/jobPostings/{job_id}",
            timeout=15
        )
        if res.status_code != 200:
            print(f"Job {job_id}: {res.status_code}")
            return None

        raw  = res.json()
        data = raw.get("data", {})
        title = data.get("title", "")
        if not title:
            return None

        posted_ms = data.get("listedAt", 0)
        post_time = ""
        if posted_ms:
            posted = datetime.fromtimestamp(int(posted_ms) / 1000)
            diff   = datetime.now() - posted
            if diff.days > 2:
                print(f"Too old ({diff.days} days) - skip")
                return None
            post_time = posted.strftime("%Y-%m-%d %H:%M")

        apply   = data.get("applyMethod", {})
        atype   = apply.get("$type", "")
        easy_apply = ""
        if "OffsiteApply" in atype:
            easy_apply = apply.get("companyApplyUrl", "")
        elif "ComplexOnsiteApply" in atype:
            easy_apply = apply.get("easyApplyUrl", "")

        location = data.get("formattedLocation", "")
        remote   = data.get("workRemoteAllowed", False)
        if remote and "remote" not in location.lower():
            location = f"Remote ({location})" if location else "Remote"

        job_type_list = data.get("employmentStatusResolutionResult", {})
        job_condition = ""
        if job_type_list:
            jt = job_type_list.get("localizedEmploymentStatus", "")
            job_condition = jt

        return {
            "title":       title,
            "description": data.get("description", {}).get("text", "")[:500],
            "location":    location,
            "job_condition": job_condition,
            "post_time":   post_time,
            "profile_url": data.get("jobPostingUrl", f"https://www.linkedin.com/jobs/view/{job_id}/"),
            "easy_apply":  easy_apply
        }
    except Exception as e:
        print(f"Job data error: {e}")
        return None

def search_posts(query: str, s: requests.Session) -> list:
    try:
        kw  = query.replace(" ", "%20")
        url = "https://www.linkedin.com/voyager/api/search/hits"
        url += "?decorationId=com.linkedin.voyager.deco.search.SearchHitV2-2"
        url += f"&count=10&keywords={kw}&origin=SWITCH_SEARCH_VERTICAL"
        url += "&q=search&start=0&type=CONTENT"
        res  = s.get(url, timeout=15)
        print(f"Posts search '{query}': {res.status_code}")
        data    = res.json()
        results = []
        elements = data.get("data", {}).get("elements", [])
        for el in elements:
            try:
                hit = el.get("hitInfo", {})
                post = hit.get("com.linkedin.voyager.search.SearchContent", {})
                text = post.get("contentDescription", "")
                actor = post.get("actor", {})
                name  = actor.get("name", {}).get("text", "")
                profile_url = ""
                nav = actor.get("navigationUrl", "")
                if nav:
                    profile_url = nav if nav.startswith("http") else f"https://www.linkedin.com{nav}"
                post_urn = post.get("targetUrn", "")
                if text and profile_url:
                    results.append({
                        "text":        text,
                        "name":        name,
                        "profile_url": profile_url,
                        "urn":         post_urn
                    })
            except Exception:
                continue
        print(f"Posts found: {len(results)}")
        return results
    except Exception as e:
        print(f"Posts search error: {e}")
        return []

def run_jobs(s, seen):
    saved = 0
    for query in JOB_QUERIES:
        time.sleep(random.uniform(3, 6))
        job_ids = search_jobs(query, s)

        for job_id in job_ids:
            url = f"https://www.linkedin.com/jobs/view/{job_id}/"
            if url in seen:
                print(f"Already seen - skip")
                continue

            data = get_job_data(job_id, s)
            if not data:
                seen[url] = time.time()
                continue

            result = is_relevant(data["title"], data["description"])
            seen[url] = time.time()

            if not result["relevant"]:
                print(f"Not relevant - skip")
                continue

            save_to_sheet({
                "A": time.strftime("%Y-%m-%d %H:%M"),
                "B": data["title"],
                "E": data["description"],
                "K": data["location"],
                "L": data["job_condition"],
                "M": "In Waiting",
                "N": "",
                "O": "Job",
                "P": data["post_time"],
                "R": data["profile_url"],
                "W": data["easy_apply"]
            })

            saved += 1
            print(f"Job saved: {data['title']} | Need: {result['need']}")
            time.sleep(random.uniform(1, 3))

    return saved

def run_posts(s, seen):
    saved = 0
    for query in POST_QUERIES:
        time.sleep(random.uniform(3, 6))
        posts = search_posts(query, s)

        for post in posts:
            url = post["profile_url"] + post["urn"]
            if url in seen:
                print(f"Already seen - skip")
                continue

            result = is_relevant(query, post["text"])
            seen[url] = time.time()

            if not result["relevant"]:
                print(f"Not relevant - skip")
                continue

            save_to_sheet({
                "A": time.strftime("%Y-%m-%d %H:%M"),
                "B": post["name"],
                "E": post["text"],
                "K": "",
                "L": "",
                "M": "In Waiting",
                "N": "",
                "O": "Post",
                "P": time.strftime("%Y-%m-%d %H:%M"),
                "R": post["profile_url"],
                "W": ""
            })

            saved += 1
            print(f"Post saved: {post['name']} | Need: {result['need']}")
            time.sleep(random.uniform(1, 3))

    return saved

print("Agent started!")
seen = load_seen()
print(f"Seen: {len(seen)}")

s = get_session()

print("\n--- JOBS ---")
jobs_saved = run_jobs(s, seen)

print("\n--- POSTS ---")
posts_saved = run_posts(s, seen)

save_seen(seen)
print(f"\nDone! Jobs: {jobs_saved} | Posts: {posts_saved}")
