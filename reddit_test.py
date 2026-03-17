import os
import asyncio
import random
from playwright.async_api import async_playwright

REDDIT_USERNAME = os.environ.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.environ.get("REDDIT_PASSWORD", "")

SUBREDDITS = ["entrepreneur", "smallbusiness", "Automate", "forhire"]
KEYWORDS   = ["need automation", "chatbot help", "workflow help", "need chatbot"]

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()

        # ── Step 1: Login
        print("🔐 Logging in...")
        await page.goto("https://www.reddit.com/login/", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # Username
        for sel in ['input[name="username"]', '#loginUsername', 'input[id*="user"]', 'input[placeholder*="username" i]']:
            el = await page.query_selector(sel)
            if el:
                await el.click()
                await asyncio.sleep(1)
                await el.fill(REDDIT_USERNAME)
                print(f"  Username filled via: {sel}")
                break

        await asyncio.sleep(1)

        # Password
        for sel in ['input[name="password"]', '#loginPassword', 'input[type="password"]']:
            el = await page.query_selector(sel)
            if el:
                await el.click()
                await asyncio.sleep(1)
                await el.fill(REDDIT_PASSWORD)
                print(f"  Password filled via: {sel}")
                break

        await asyncio.sleep(1)

        # Submit
        for sel in ['button[type="submit"]', 'button:has-text("Log In")', 'button:has-text("Login")']:
            btn = await page.query_selector(sel)
            if btn:
                await btn.click()
                print(f"  Submit via: {sel}")
                break

        await asyncio.sleep(6)
        print(f"  URL after login: {page.url}")

        if "login" in page.url:
            print("❌ Login failed!")
            await browser.close()
            return

        print("✅ Login successful!\n")

        found_posts = []

        # ── Step 2: Subreddits
        print("="*50)
        print("SCANNING SUBREDDITS")
        print("="*50)

        for sub in SUBREDDITS:
            print(f"\n📌 r/{sub}")
            await page.goto(f"https://www.reddit.com/r/{sub}/new/", wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(2)

            posts = await page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll(
                        'article, shreddit-post, [data-testid="post-container"]'
                    );
                    for (const item of items) {
                        const titleEl = item.querySelector(
                            'h3, h1, a[slot="title"], [id*="post-title"]'
                        );
                        const title = titleEl ? titleEl.innerText.trim() : '';
                        const linkEl = item.querySelector('a[href*="/r/"][href*="/comments/"]');
                        const url    = linkEl ? linkEl.href : '';
                        if (title && url) results.push({ title, url });
                    }
                    return results.slice(0, 10);
                }
            """)

            print(f"  Found: {len(posts)} posts")
            for post in posts[:5]:
                print(f"  → {post['title'][:80]}")
                found_posts.append({"source": f"r/{sub}", **post})

            await asyncio.sleep(2)

        # ── Step 3: Keywords
        print("\n" + "="*50)
        print("KEYWORD SEARCH")
        print("="*50)

        for keyword in KEYWORDS:
            print(f"\n🔍 '{keyword}'")
            await page.goto(
                f"https://www.reddit.com/search/?q={keyword.replace(' ', '+')}&sort=new",
                wait_until="domcontentloaded"
            )
            await asyncio.sleep(3)

            posts = await page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll(
                        'article, shreddit-post, [data-testid="post-container"]'
                    );
                    for (const item of items) {
                        const titleEl = item.querySelector(
                            'h3, h1, a[slot="title"], [id*="post-title"]'
                        );
                        const title = titleEl ? titleEl.innerText.trim() : '';
                        const linkEl = item.querySelector('a[href*="/r/"][href*="/comments/"]');
                        const url    = linkEl ? linkEl.href : '';
                        if (title && url) results.push({ title, url });
                    }
                    return results.slice(0, 5);
                }
            """)

            print(f"  Found: {len(posts)} posts")
            for post in posts[:3]:
                print(f"  → {post['title'][:80]}")
                found_posts.append({"source": f"keyword:{keyword}", **post})

            await asyncio.sleep(2)

        # ── Summary
        print("\n" + "="*50)
        print(f"✅ TOTAL POSTS FOUND: {len(found_posts)}")
        print("="*50)
        for i, post in enumerate(found_posts, 1):
            print(f"{i}. [{post['source']}] {post['title'][:70]}")

        await browser.close()

asyncio.run(run())
