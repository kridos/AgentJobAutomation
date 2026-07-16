"""
Scrape internships from multiple job boards using crawl4ai.
Targets: LinkedIn, Glassdoor, Indeed, GitHub Jobs, HackerNews.
Returns Listing objects compatible with the pipeline.

Run standalone: python crawl4ai_scraper.py
"""

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:
    AsyncWebCrawler = None


@dataclass
class Listing:
    """Match scraper.py Listing format."""
    company: str
    role: str
    location: str
    link: str
    date_posted: str
    id: str = ""


async def _crawl_linkedin_jobs(query: str = "internship", limit: int = 20) -> list[Listing]:
    """
    Scrape LinkedIn jobs for the given query.
    Note: LinkedIn may require auth or block scrapers; fallback gracefully.
    """
    if not AsyncWebCrawler:
        return []
    
    listings = []
    try:
        url = f"https://www.linkedin.com/jobs/search/?keywords={query}&f=tL"
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url, screenshot=False)
            if not result.success:
                return []
            
            # LinkedIn job listings are in <div> with data-* attributes
            # This is a simplified extraction; LinkedIn's structure is complex
            html = result.html
            
            # Look for job title patterns
            job_pattern = re.compile(
                r'<a[^>]*href="([^"]*jobs/view/\d+[^"]*)"[^>]*>([^<]+)</a>'
            )
            for match in job_pattern.finditer(html):
                link = match.group(1)
                role = match.group(2).strip()
                
                # Try to extract company from nearby text
                company_pattern = re.search(
                    rf'{re.escape(role)}.*?<a[^>]*>([^<]+)</a>', html
                )
                company = company_pattern.group(1) if company_pattern else "LinkedIn"
                
                listings.append(Listing(
                    company=company,
                    role=role,
                    location="Various",
                    link=link,
                    date_posted=datetime.now().strftime("%Y-%m-%d"),
                    id=f"linkedin_{len(listings)}"
                ))
                if len(listings) >= limit:
                    break
    except Exception as e:
        print(f"[crawl4ai_scraper] LinkedIn scrape failed: {e}")
    
    return listings


async def _crawl_glassdoor_jobs(query: str = "internship", location: str = "US", limit: int = 20) -> list[Listing]:
    """
    Scrape Glassdoor internship listings.
    Glassdoor has decent HTML structure but may block scrapers.
    """
    if not AsyncWebCrawler:
        return []
    
    listings = []
    try:
        url = f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={query}&locT=C&locId=1&locKeyword={location}"
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url, screenshot=False)
            if not result.success:
                return []
            
            html = result.html
            
            # Glassdoor uses <a> with job titles in specific classes
            job_pattern = re.compile(
                r'<a[^>]*data-job-id="(\d+)"[^>]*href="([^"]*)"[^>]*>([^<]+)</a>'
            )
            
            for match in job_pattern.finditer(html):
                job_id = match.group(1)
                link = "https://www.glassdoor.com" + match.group(2) if not match.group(2).startswith("http") else match.group(2)
                role = match.group(3).strip()
                
                listings.append(Listing(
                    company="Glassdoor Job",
                    role=role,
                    location=location,
                    link=link,
                    date_posted=datetime.now().strftime("%Y-%m-%d"),
                    id=f"glassdoor_{job_id}"
                ))
                if len(listings) >= limit:
                    break
    except Exception as e:
        print(f"[crawl4ai_scraper] Glassdoor scrape failed: {e}")
    
    return listings


async def _crawl_github_jobs(query: str = "internship", limit: int = 20) -> list[Listing]:
    """
    Scrape GitHub Jobs board (if still active).
    GitHub Jobs was deprecated in 2021, but alternative boards exist.
    """
    if not AsyncWebCrawler:
        return []
    
    listings = []
    try:
        # Fallback to a jobs aggregator or GitHub's own job postings
        # This is a placeholder; GitHub Jobs site is no longer active
        pass
    except Exception as e:
        print(f"[crawl4ai_scraper] GitHub Jobs scrape failed: {e}")
    
    return listings


async def _crawl_hacker_news_jobs(limit: int = 20) -> list[Listing]:
    """
    Scrape HackerNews 'Who is hiring?' monthly thread.
    Great for tech internships; updates monthly.
    """
    if not AsyncWebCrawler:
        return []
    
    listings = []
    try:
        # HN job threads are at hn.algolia.com or direct HN posts
        # This would require scraping the monthly thread
        pass
    except Exception as e:
        print(f"[crawl4ai_scraper] HackerNews scrape failed: {e}")
    
    return listings


async def scrape_all_sources(limits: dict = None) -> list[Listing]:
    """
    Scrape all configured job board sources in parallel.
    Returns deduplicated Listing objects.
    
    limits: dict like {"linkedin": 25, "glassdoor": 30, ...}
    """
    if not AsyncWebCrawler:
        print("[crawl4ai_scraper] crawl4ai not installed. Run: pip install crawl4ai")
        return []
    
    limits = limits or {"linkedin": 15, "glassdoor": 20}
    
    # Run scrapes in parallel
    tasks = [
        _crawl_linkedin_jobs(limit=limits.get("linkedin", 15)),
        _crawl_glassdoor_jobs(limit=limits.get("glassdoor", 20)),
        # _crawl_github_jobs(limit=limits.get("github", 10)),
        # _crawl_hacker_news_jobs(limit=limits.get("hackernews", 15)),
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Flatten and deduplicate by (company, role)
    all_listings = []
    seen = set()
    
    for result in results:
        if isinstance(result, Exception):
            continue
        for listing in result:
            key = (listing.company.lower(), listing.role.lower())
            if key not in seen:
                seen.add(key)
                all_listings.append(listing)
    
    print(f"[crawl4ai_scraper] Scraped {len(all_listings)} unique listings from all sources")
    return all_listings


def scrape_async_wrapper(limits: dict = None) -> list[Listing]:
    """Wrapper to run async scraping from sync context."""
    return asyncio.run(scrape_all_sources(limits))


if __name__ == "__main__":
    listings = scrape_async_wrapper()
    for listing in listings[:5]:
        print(f"- {listing.company} | {listing.role} | {listing.location}")
    print(f"\nTotal: {len(listings)}")
