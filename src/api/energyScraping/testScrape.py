"""
Simple tariff scraper using Selenium (real browser)
"""

from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

# Debug output dir (same as ScrapeTariff)
_DEBUG_DIR = Path(__file__).resolve().parents[3] / "output" / "scrape_debug"

# URL to scrape
url = "https://www.moneysupermarket.com/gas-and-electricity/"

print(f"Opening browser and navigating to: {url}")

try:
    # Set up Chrome driver (downloads driver automatically)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

    # Navigate to the page
    driver.get(url)

    # Wait for page to load
    print("Waiting for page to load...")
    time.sleep(5)

    print(f"✅ Page loaded successfully")
    print(f"Page title: {driver.title}")

    # Get the page HTML
    html = driver.page_source

    # Parse with BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')

    # Save to file
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    out = _DEBUG_DIR / 'scraped_page.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(soup.prettify())
    print(f"💾 Saved HTML to '{out}'")

    # Try to find some data
    print("\n--- Sample data from page ---")

    # Look for headings
    headings = soup.find_all(['h1', 'h2', 'h3'], limit=5)
    print(f"Found {len(headings)} headings:")
    for h in headings[:5]:
        print(f"  - {h.get_text(strip=True)[:100]}")

    # Look for any tariff-related elements
    print(f"\nHTML size: {len(html)} bytes")

    # Keep browser open for 3 seconds so you can see it
    print("\nBrowser will close in 3 seconds...")
    time.sleep(3)

    # Close browser
    driver.quit()
    print("✅ Browser closed")

except Exception as e:
    print(f"❌ Error: {e}")
    if 'driver' in locals():
        driver.quit()

print("\n✅ Script finished - check output/scrape_debug/scraped_page.html")