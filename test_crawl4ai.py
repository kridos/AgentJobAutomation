"""
Quick test of crawl4ai_scraper.py before enabling in the full pipeline.

Run: python test_crawl4ai.py

This will attempt to scrape a few job boards and print results.
If successful, you can enable crawl4ai in config.yaml under 'crawl4ai.enabled: true'
"""

if __name__ == "__main__":
    try:
        import crawl4ai
        print("✓ crawl4ai is installed")
    except ImportError:
        print("✗ crawl4ai not installed")
        print("   Install with: pip install crawl4ai")
        exit(1)
    
    try:
        from crawl4ai_scraper import scrape_async_wrapper
        
        print("\n[test] Scraping job boards (this may take a minute)...\n")
        listings = scrape_async_wrapper(limits={"linkedin": 5, "glassdoor": 5})
        
        if listings:
            print(f"✓ Found {len(listings)} listings:\n")
            for i, listing in enumerate(listings[:10], 1):
                print(f"{i}. {listing.company:25s} | {listing.role:40s} | {listing.location}")
            
            print(f"\n✓ crawl4ai_scraper is working!")
            print("\nTo enable crawl4ai in the pipeline:")
            print("  1. Edit config.yaml")
            print("  2. Set crawl4ai.enabled: true")
            print("  3. Adjust limits as desired (linkedin, glassdoor, etc.)")
            print("  4. Run: automator run")
        else:
            print("⚠ No listings found (job boards may have blocked scraper or changed structure)")
            print("  This is normal — scrapers are fragile due to site changes")
    
    except Exception as e:
        print(f"✗ Error: {e}")
        print("\nTroubleshooting:")
        print("  - Check that crawl4ai is installed: pip install crawl4ai")
        print("  - Check internet connection")
        print("  - Check if job board sites are blocking scrapers")
