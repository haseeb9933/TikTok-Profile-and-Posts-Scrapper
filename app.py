import re, json, time
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
app = FastAPI(title="TikTok Scraper API")

def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1600")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def parse_count(text: str):
    if not text:
        return None
    text = text.strip().upper()
    if text.endswith("K"):
        return int(float(text[:-1]) * 1000)
    elif text.endswith("M"):
        return int(float(text[:-1]) * 1000000)
    elif text.endswith("B"):
        return int(float(text[:-1]) * 1000000000)
    else:
        return int(text.replace(",", ""))

def scrape_post_details(driver, username, post_id):
    url = f"https://www.tiktok.com/@{username}/video/{post_id}"
    driver.get(url)
    time.sleep(2)
    
    try:
        likes = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="like-count"]').text)
    except:
        likes = None
    
    try:
        comments = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="comment-count"]').text)
    except:
        comments = None
    
    try:
        shares = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="share-count"]').text)
    except:
        shares = None
    
    views, timestamp, description = None, None, None
    hashtags = []
    try:
        soup = BeautifulSoup(driver.page_source, "lxml")
        script = soup.select_one("script#SIGI_STATE")
        if script:
            data = json.loads(script.text)
            item = data.get("ItemModule", {}).get(str(post_id), {})
            stats = item.get("stats", {})
            views = int(stats.get("playCount", 0))
            timestamp = item.get("createTime")
            description = item.get("desc")
            if description:
                hashtags = re.findall(r"#\w+", description)
    except:
        pass
    return {
        "post_id": post_id,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "views": views,
        "timestamp": timestamp,
        "description": description,
        "hashtags": hashtags,
    }

@app.get("/profile")
def scrape_profile(username: str = Query(...), max_posts: int = Query(5, ge=1, le=20)):
    driver = create_driver()
    url = f"https://www.tiktok.com/@{username}"
    driver.get(url)
    time.sleep(2)
    
    try:
        bio = driver.find_element(By.CSS_SELECTOR, 'h2[data-e2e="user-bio"]').text
    except:
        bio = None
    try:
        followers = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="followers-count"]').text)
    except:
        followers = None
    try:
        following = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="following-count"]').text)
    except:
        following = None
    try:
        likes = parse_count(driver.find_element(By.CSS_SELECTOR, 'strong[data-e2e="likes-count"]').text)
    except:
        likes = None
   
    post_ids = []
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]')
        for el in elements:
            href = el.get_attribute("href")
            if href and "/video/" in href:
                pid = href.split("/")[-1]
                if pid not in post_ids:
                    post_ids.append(pid)
            if len(post_ids) >= max_posts:
                break
    except:
        pass
    
    posts = []
    for pid in post_ids:
        try:
            posts.append(scrape_post_details(driver, username, pid))
        except Exception as e:
            print(f"Error scraping post {pid}: {e}")
    driver.quit()
    return {
        "profile": {
            "username": username,
            "bio": bio,
            "followers": followers,
            "following": following,
            "likes": likes
        },
        "posts": posts
    }