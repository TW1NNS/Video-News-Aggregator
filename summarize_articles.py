import json
import sqlite3
import time
import requests
from bs4 import BeautifulSoup
import openai
import schedule
import os
import traceback

# --- Load config ---
with open('config.json') as f:
    cfg = json.load(f)

# Use GitHub secret if available
openai.api_key = os.getenv('OPENAI_API_KEY') or cfg['openai_api_key']

# --- Database setup ---
def init_db(path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY,
            site TEXT,
            title TEXT,
            url TEXT,
            summary TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# --- Scraping helpers ---
def fetch_article_urls(site):
    r = requests.get(site['base_url'])
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    links = []
    for a in soup.select(site['article_list_selector']):
        href = a.get('href')
        if href and href.startswith('http'):
            links.append({'url': href, 'title': a.get_text(strip=True)})
        if len(links) >= cfg['max_articles']:
            break
    return links

def fetch_article_content(url, selector):
    r = requests.get(url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    elem = soup.select_one(selector)
    return elem.get_text(separator=' ', strip=True) if elem else ''

# --- Summarization ---
def summarize(text):
    prompt = f"Summarize this article in detail:\n\n{text[:1500]}"
    resp = openai.ChatCompletion.create(
        model='gpt-4o',
        messages=[{'role':'user','content':prompt}]
    )
    return resp.choices[0].message.content

# --- Save to DB ---
def save_article(site_name, title, url, summary):
    conn = sqlite3.connect(cfg['database_path'])
    c = conn.cursor()
    c.execute(
        'INSERT INTO articles (site, title, url, summary) VALUES (?, ?, ?, ?)',
        (site_name, title, url, summary)
    )
    conn.commit()
    conn.close()

# --- Main job ---
def job():
    print("Starting weekly scrape & summarize...")
    init_db(cfg['database_path'])
    for site in cfg['sites']:
        print(f"Processing {site['name']}...")
        try:
            articles = fetch_article_urls(site)
            for art in articles:
                content = fetch_article_content(art['url'], site['content_selector'])
                summary = summarize(content)
                save_article(site['name'], art['title'], art['url'], summary)
                time.sleep(1)
        except Exception as e:
            print(f"Error on {site['name']}: {e}")
            traceback.print_exc()
    print("Done.")

# --- Scheduler (when run locally) ---
if __name__ == '__main__':
    schedule.every().monday.at('08:00').do(job)
    print("Scheduler started. Waiting for next run...")
    while True:
        schedule.run_pending()
        time.sleep(30)
