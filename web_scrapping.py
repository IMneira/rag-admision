import os
import time
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
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "_")
    if not path:
        path = "home"
    max_length = 100
    if len(path) > max_length:
        path = path[:max_length]
    return path

def save_text(content, filename):
    os.makedirs(DATA_PATH, exist_ok=True)
    with open(os.path.join(DATA_PATH, f"{filename}.txt"), "w", encoding="utf-8") as f:
        f.write(content)

def scrape_page(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] No se pudo acceder a {url}: {e}")
        return "", set([])

    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        print(f"[AVISO] Contenido no HTML en {url} (Content-Type: {content_type}). Se omite.")
        return "", set([])

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    links = extract_links(soup, url)
    return text, links

def main():
    while unvisited_urls:
        current_url = unvisited_urls.pop(0)

        if current_url in visited_urls:
            continue

        print(f"[INFO] Scrapeando: {current_url}")
        text, links = scrape_page(current_url)

        if text:
            filename = clean_filename(current_url)
            save_text(text, filename)

        visited_urls.add(current_url)
        new_links = links - visited_urls
        unvisited_urls.extend(new_links - set(unvisited_urls))

        time.sleep(WAIT_TIME)

    print("[FIN] Scraping completo.")
    
if __name__ == "__main__":
    main()