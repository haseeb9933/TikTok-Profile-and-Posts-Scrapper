import re
import json
import time
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

app = FastAPI(title="TikTok Scraper API")

# SETUP DRIVER
def create_driver():
    """Initializes and returns a Selenium Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1600")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# HELPER
def parse_count(text: str):
    """Converts formatted numbers (e.g., '10.5K', '2.1M') to integers."""
    if not text:
        return None
    text = str(text).strip().upper()
    if 'K' in text:
        return int(float(text.replace('K', '')) * 1000)
    elif 'M' in text:
        return int(float(text.replace('M', '')) * 1_000_000)
    elif 'B' in text:
        return int(float(text.replace('B', '')) * 1_000_000_000)
    else:
        try:
            return int(str(text).replace(",", ""))
        except (ValueError, AttributeError):
            return None

# SCRAPE POST 
def scrape_post_details(driver, username, post_id: str):
    """Scrapes all details from an individual TikTok post page."""
    url = f"https://www.tiktok.com/@{username}/video/{post_id}"
    driver.get(url)
    
    post_data = {
        "post_id": post_id, "likes": None, "comments": None, "shares": None,
        "views": None, "timestamp": None, "description": None, "hashtags": []
    }

    try:
        # Wait for the main data script to be present in the page
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "__UNIVERSAL_DATA_FOR_REHYDRATION__"))
        )
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # CORRECTED: Find the main data script by its ID
        script_tag = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")
        
        if script_tag:
            data = json.loads(script_tag.string)
            # Navigate to the item details within the JSON
            item_module = data.get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {}).get("itemInfo", {}).get("itemStruct", {})

            if item_module:
                stats = item_module.get("stats", {})
                post_data["likes"] = stats.get("diggCount")
                post_data["comments"] = stats.get("commentCount")
                # CORRECTED: The key for shares is often 'shareCount' or sometimes 'repostCount'
                post_data["shares"] = stats.get("shareCount")
                post_data["views"] = stats.get("playCount")
                post_data["timestamp"] = item_module.get("createTime")
                post_data["description"] = item_module.get("desc")
                
                if post_data["description"]:
                    post_data["hashtags"] = re.findall(r"#\w+", post_data["description"])
            else:
                 print(f"Could not find 'itemStruct' in JSON for post {post_id}")
        else:
            print(f"Could not find data script for post {post_id}")

    except (TimeoutException, json.JSONDecodeError, KeyError, Exception) as e:
        print(f"An error occurred while scraping post {post_id}: {e}")

    return post_data

# SCRAPE PROFILE + POSTS
@app.get("/profile")
def scrape_profile(username: str = Query(..., description="The TikTok username to scrape."), max_posts: int = Query(5, ge=1, le=20, description="Maximum number of recent posts to scrape.")):
    driver = create_driver()
    url = f"https://www.tiktok.com/@{username}"
    
    try:
        driver.get(url)
        # Wait for the profile page to load by checking for the video grid
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-e2e="user-post-item"]'))
        )
    except TimeoutException:
        driver.quit()
        return {"error": f"Profile @{username} not found or page did not load."}

    # Profile Info
    try: bio = driver.find_element(By.CSS_SELECTOR, 'h2[data-e2e="user-bio"]').text
    except: bio = None
    try: followers = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="followers-count"]').text)
    except: followers = None
    try: following = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="following-count"]').text)
    except: following = None
    try: likes = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="likes-count"]').text)
    except: likes = None

    # Scroll to load posts
    post_ids = set()
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        for _ in range(6): 
            body.send_keys(Keys.END)
            time.sleep(2)
            elements = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]')
            for el in elements:
                href = el.get_attribute("href")
                if href and "/video/" in href:
                    pid = href.split("/")[-1].split("?")[0]
                    post_ids.add(pid)
            if len(post_ids) >= max_posts:
                break
    except Exception as e:
        print(f"Error collecting post IDs: {e}")

    # Scrape each post
    posts = []
    for pid in list(post_ids)[:max_posts]:
        try:
            post_details = scrape_post_details(driver, username, pid)
            if post_details:
                posts.append(post_details)
        except Exception as e:
            print(f"Error scraping post {pid}: {e}")

    driver.quit()

    return {
        "profile": {
            "username": username, "bio": bio, "followers": followers,
            "following": following, "likes": likes
        },
        "posts": posts
    }