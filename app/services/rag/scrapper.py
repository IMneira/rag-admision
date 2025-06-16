import json
import os
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

URL_BASE = "https://admision.uandes.cl"
DATA_PATH = "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ChatbotScraper/1.0)"}
WAIT_TIME = 2

visited_urls = set()
unvisited_urls = [URL_BASE]


def is_same_domain(url):
    return urlparse(url).netloc.endswith("admision.uandes.cl")

def extract_links(soup, base_url):
    links = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        full_url = urljoin(base_url, href)
        if is_same_domain(full_url):
            links.add(full_url.split("#")[0])
    return links

def clean_filename(url):
    hashed = hashlib.md5(url.encode("utf-8")).hexdigest()
    return hashed

def save_text(content, filename):
    os.makedirs(DATA_PATH, exist_ok=True)
    with open(os.path.join(DATA_PATH, f"{filename}.txt"), "w", encoding="utf-8") as f:
        f.write(content)

def scrape_page(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Could not access {url}: {e}")
        return "", set([])

    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        print(f"[NOTICE] Non-HTML content at {url} (Content-Type: {content_type}). Skipping.")
        return "", set([])

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    links = extract_links(soup, url)
    return text, links

def main():
    index_mapping = {}
    start_time = time.time()
    while unvisited_urls:
        current_url = unvisited_urls.pop(0)

        if current_url in visited_urls:
            continue

        print(f"[INFO] Scraping: {current_url}")
        text, links = scrape_page(current_url)

        if text:
            filename = clean_filename(current_url)
            save_text(text, filename)
            index_mapping[filename] = current_url

        visited_urls.add(current_url)
        new_links = links - visited_urls
        unvisited_urls.extend(new_links - set(unvisited_urls))

        time.sleep(WAIT_TIME)

    with open(os.path.join(DATA_PATH, "url_index.json"), "w", encoding="utf-8") as index_file:
        json.dump(index_mapping, index_file, indent=2, ensure_ascii=False)

    duration = time.time() - start_time
    print(f"[END] Scraping completed in {duration:.2f} seconds.")    

if __name__ == "__main__":
    main()