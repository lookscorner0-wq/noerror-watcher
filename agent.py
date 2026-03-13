import os
import json
import time
import random
import re
import requests
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

LI_AT         = os.environ["LI_AT"]
LI_JSESSIONID = os.environ["LI_JSESSIONID"]
OPENAI_KEY    = os.environ["OPENAI_KEY"]
SHEET_URL     = os.environ["SHEET_URL"]
SEEN_FILE     = "seen_urls.json"

QUERIES = [
    "AI Automation Expert",
    "Social Media Marketing Manager",
    "Chatbot Developer",
    "Custom Flow Workflow Builder"
]

SYSTEM_PROMPT = (
    "You are a lead qualification expert for LooksCorner, a digital agency in Pakistan. "
    "We offer: AI Automation, Chatbot Development, Social Media Marketing, Workflow Building (N8N/Make), Lead Generation, Cold Email-Whatsapp Calling, Social Media Automation, personal Chatbots, leads Booking-Meetings Bots, Business Automating. "
    "RELEVANT: company is actively looking to OUTSOURCE or HIRE FREELANCER/AGENCY "
    "for any digital, tech, or marketing service. Even if not directly our service, "
    "if they seem like a business that COULD need our services — mark relevant. "
    "NOT RELEVANT: pure employee hiring (data entry, HR, driver, teacher), web design/development only. "
    "Reply ONLY in this exact format:\n"
    "relevant: yes\n"
    "OR\n"
    "relevant: no"
)

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def get_client_type(description):
    desc = description.lower()
    if any(x in desc for x in ["enterprise", "fortune", "global leader", "publicly traded", "10,000", "multinational"]):
        return "Oppertunity"
    if any(x in desc for x in ["startup", "growing", "series a", "series b", "saas", "scale up", "mid-size"]):
        return "GoodClient"
    return "Main Client"

def get_session():
    s = requests.Session()
    s.headers.update({
        "accept": "application/vnd.linkedin.normalized+json+2.1",
        "csrf-token": LI_JSESSIONID,
        "referer": "https://www.linkedin.com/jobs/search/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "x-li-lang": "en_US",
        "x-restli-protocol-version": "2.0.0",
        "x-li-deco-include-micro-schema": "true",
        "cookie": f'JSESSIONID="{LI_JSESSIONID}"; li_at={LI_AT}'
    })
    return s

def search_jobs(query, s):
    try:
        kw  = query.replace(" ", "%20")
        url = "https://www.linkedin.com/voyager/api/voyagerJobsDashJobCards"
        url += "?decorationId=com.linkedin.voyager.dash.deco.jobs.search.JobSearchCardsCollectionLite-88"
        url += "&count=5&q=jobSearch"
        url += f"&query=(origin:JOBS_HOME_SEARCH_BUTTON,keywords:{kw},locationUnion:(geoId:92000000),spellCorrectionEnabled:true)"
        url += "&servedEventEnabled=false&start=0&f_TPR=r259200"
        res  = s.get(url)
        print(f"Search '{query}': {res.status_code}")
        data = res.json()
        cards = data.get("data", {}).get("metadata", {}).get("jobCardPrefetchQueries", [])
        ids  = []
        for card in cards:
            for key in card.get("prefetchJobPostingCard", {}).keys():
                match = re.search(r'\((\d+),', key)
                if match:
                    ids.append(match.group(1))
        print(f"Job IDs: {ids}")
        return ids
    except Exception as e:
        print(f"Search error: {e}")
        return []

def get_job_data(job_id, s):
    try:
        time.sleep(random.uniform(2, 4))
        res = s.get(
            f"https://www.linkedin.com/voyager/api/jobs/jobPostings/{job_id}",
            headers={
                "accept": "application/vnd.linkedin.normalized+json+2.1",
                "csrf-token": LI_JSESSIONID,
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
                "x-restli-protocol-version": "2.0.0",
                "cookie": f'JSESSIONID="{LI_JSESSIONID}"; li_at={LI_AT}'
            }
        )
        if res.status_code != 200:
            print(f"Job {job_id}: {res.status_code}")
            return None

        raw  = res.json()
        data = raw.get("data", {})
        title = data.get("title", "")
        print(f"Job {job_id} | Title: {title}")
        if not title:
            return None

        listed_at = data.get("listedAt", "")
        job_time  = ""
        if listed_at:
            posted = datetime.fromtimestamp(int(listed_at) / 1000)
            diff   = datetime.now() - posted
            if diff > timedelta(hours=72):
                print(f"Too old ({diff}) — skip!")
                return None
            job_time = posted.strftime("%H:%M")

        apply    = data.get("applyMethod", {})
        atype    = apply.get("$type", "")
        external = apply.get("companyApplyUrl", "") if "OffsiteApply" in atype else ""
        easy     = apply.get("easyApplyUrl", "") if "ComplexOnsiteApply" in atype else ""

        location = data.get("formattedLocation", "")
        remote   = data.get("workRemoteAllowed", False)
        if remote and "remote" not in location.lower():
            location = f"Remote ({location})" if location else "Remote"

        emp = data.get("employmentStatus", "")
        job_condition = ""
        if emp:
            last = emp.split(":")[-1]
            type_map = {
                "FULL_TIME": "Full Time", "PART_TIME": "Part Time",
                "CONTRACT": "Contract", "TEMPORARY": "Temporary",
                "INTERNSHIP": "Internship", "VOLUNTEER": "Volunteer", "OTHER": "Other"
            }
            job_condition = type_map.get(last, last)

        return {
            "title":         title,
            "description":   data.get("description", {}).get("text", "")[:300],
            "location":      location,
            "job_condition": job_condition,
            "job_time":      job_time,
            "profile_url":   data.get("jobPostingUrl", f"https://www.linkedin.com/jobs/view/{job_id}/"),
            "apply_url":     data.get("apply_url", external if external else easy)
        }
    except Exception as e:
        print(f"Job data error: {e}")
        return None

def qualify_job(title, description):
    try:
        user_prompt = f"Job Title: {title}\nJob Description: {description[:300]}"
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt}
                ],
                "temperature": 0.1,
                "max_tokens":  10
            }
        )
        answer = res.json()["choices"][0]["message"]["content"].strip().lower()
        print(f"AI '{title[:35]}': {answer}")
        return "relevant: yes" in answer
    except Exception as e:
        print(f"LLM error: {e}")
        return True

def save_to_sheet(row):
    try:
        res = requests.post(SHEET_URL, json=row)
        print(f"Sheet: {res.text}")
    except Exception as e:
        print(f"Sheet error: {e}")

def run_watcher():
    seen = load_seen()
    s    = get_session()

    for query in QUERIES:
        time.sleep(random.uniform(3, 6))
        job_ids = search_jobs(query, s)

        for job_id in job_ids:
            url = f"https://www.linkedin.com/jobs/view/{job_id}/"
            if url in seen:
                print(f"Skip {job_id}!")
                continue

            data = get_job_data(job_id, s)
            if not data:
                continue

            relevant = qualify_job(data.get("title", ""), data.get("description", ""))
            if not relevant:
                print(f"Not relevant — skip!")
                continue

            client_type = get_client_type(data.get("description", ""))

            save_to_sheet({
                "timestamp":     time.strftime("%Y-%m-%d %H:%M"),
                "title":         data.get("title", ""),
                "description":   data.get("description", ""),
                "location":      data.get("location", ""),
                "job_condition": data.get("job_condition", ""),
                "lead_status":   "In Pending",
                "lead_type":     "",
                "client_type":   client_type,
                "job_time":      data.get("job_time", ""),
                "profile_url":   data.get("profile_url", url),
                "apply_url":     data.get("apply_url", "")
            })
            seen.add(url)
            print(f"Saved '{data.get('title')}'! Client: {client_type}")
            time.sleep(random.uniform(1, 3))

    save_seen(seen)
    print("Done!")

# =============================
# Keep alive for Leapcell
# =============================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, format, *args):
        pass

def run_server():
    server = HTTPServer(('0.0.0.0', 8080), Handler)
    server.serve_forever()

# Server alag thread mein start karo
threading.Thread(target=run_server, daemon=True).start()

# Watcher loop — har 1 ghante mein run karo
while True:
    print(f"\n--- Watcher Run: {datetime.now().strftime('%Y-%m-%d %H:%M')} ---")
    run_watcher()
    print("Sleeping 1 hour...")
    time.sleep(3600)
