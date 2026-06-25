"""
Web research on company + role using browser-use + playwright.
Wrapped in try/except — failures are non-fatal.
Run standalone: python researcher.py "Stripe" "Software Engineering Intern"
"""

import asyncio
import sys
from typing import Optional


async def _research_async(company: str, role: str, timeout_seconds: int = 30) -> str:
    """Use browser-use to research the company and role."""
    try:
        from browser_use import Agent as BrowserAgent
        from browser_use.browser.browser import Browser, BrowserConfig
    except ImportError:
        return ""

    query = (
        f"Research {company} for a {role} internship application. "
        f"Find: their main tech stack, recent engineering blog posts or projects, "
        f"company culture and values, what they look for in interns. "
        f"Be concise — bullet points preferred."
    )

    try:
        # Use a headless browser
        browser = Browser(config=BrowserConfig(headless=True))
        agent = BrowserAgent(
            task=query,
            llm=None,  # browser-use requires an LLM — we'll use a minimal local one
            browser=browser,
            max_actions_per_step=5,
        )
        result = await asyncio.wait_for(agent.run(), timeout=timeout_seconds)
        await browser.close()

        if hasattr(result, "final_result"):
            return result.final_result() or ""
        return str(result)
    except asyncio.TimeoutError:
        print(f"[researcher] Timeout researching {company}", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"[researcher] browser-use error for {company}: {e}", file=sys.stderr)
        return ""


async def _research_playwright_fallback(company: str, role: str) -> str:
    """Lightweight fallback: fetch company homepage and extract text."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ""

    search_url = f"https://www.google.com/search?q={company}+{role.replace(' ', '+')}+internship+tech+stack+engineering"

    text_chunks = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(search_url, timeout=15000)
            await page.wait_for_load_state("domcontentloaded")
            # Extract visible text from search results
            content = await page.evaluate("() => document.body.innerText")
            text_chunks.append(content[:3000])
            await browser.close()
    except Exception as e:
        print(f"[researcher] Playwright fallback error: {e}", file=sys.stderr)

    if not text_chunks:
        return ""

    combined = "\n".join(text_chunks)
    return f"## Web Research (search results)\n{combined[:2000]}"


def research(company: str, role: str, timeout_seconds: int = 30) -> str:
    """
    Research company + role for internship context.
    Returns a markdown string, or empty string if research fails.
    Never raises — always safe to call.
    """
    try:
        result = asyncio.run(_research_async(company, role, timeout_seconds))
        if result:
            return f"## Company Research: {company}\n{result}"
    except Exception as e:
        print(f"[researcher] browser-use failed, trying playwright fallback: {e}", file=sys.stderr)

    try:
        result = asyncio.run(_research_playwright_fallback(company, role))
        return result
    except Exception as e:
        print(f"[researcher] All research methods failed for {company}: {e}", file=sys.stderr)
        return ""


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "Stripe"
    role = sys.argv[2] if len(sys.argv) > 2 else "Software Engineering Intern"
    print(f"Researching {company} for role: {role}\n")
    result = research(company, role)
    if result:
        print(result)
    else:
        print("No research results (browser-use/playwright may not be configured).")
