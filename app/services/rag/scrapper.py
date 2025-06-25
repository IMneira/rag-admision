import json
import os
import time
import hashlib
import requests
import html2text
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pypdf import PdfReader
import io

URL_BASE = "https://admision.uandes.cl"
DATA_PATH = "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ChatbotScraper/1.0)"}
WAIT_TIME = 0.5

visited_urls = set()
unvisited_urls = [URL_BASE]

# Initialize html2text converter
h2t = html2text.HTML2Text()
h2t.ignore_links = False
h2t.ignore_images = True
h2t.body_width = 0  # Don't wrap lines


def is_same_domain(url):
    return urlparse(url).netloc.endswith("admision.uandes.cl")


def is_pdf_url(url):
    """Check if URL points to a PDF file"""
    return url.lower().endswith('.pdf')


def extract_links(soup, base_url):
    links = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        full_url = urljoin(base_url, href)
        if is_same_domain(full_url):
            # Remove fragment identifiers
            clean_url = full_url.split("#")[0]
            if clean_url:  # Only add non-empty URLs
                links.add(clean_url)
    return links


def clean_filename(url):
    hashed = hashlib.md5(url.encode("utf-8")).hexdigest()
    return hashed


def extract_pdf_text(pdf_content):
    """Extract text from PDF content"""
    try:
        pdf_file = io.BytesIO(pdf_content)
        pdf_reader = PdfReader(pdf_file)
        
        # Build markdown content
        markdown_content = f"# PDF Document\n\n"
        markdown_content += f"**Total Pages:** {len(pdf_reader.pages)}\n\n"
        markdown_content += "---\n\n"
        
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            if page_text:
                markdown_content += f"## Page {page_num + 1}\n\n"
                # Clean up text and preserve paragraph structure
                paragraphs = page_text.split('\n\n')
                for para in paragraphs:
                    cleaned_para = ' '.join(para.split())
                    if cleaned_para:
                        markdown_content += f"{cleaned_para}\n\n"
                markdown_content += "---\n\n"
        
        return markdown_content.strip()
    except Exception as e:
        print(f"[ERROR] Failed to extract PDF text: {e}")
        return ""


def html_to_markdown(soup, url):
    """Convert HTML soup to well-formatted Markdown"""
    try:
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get the title
        title = soup.find('title')
        title_text = title.get_text(strip=True) if title else "Untitled"
        
        # Convert to markdown
        html_content = str(soup)
        markdown_content = h2t.handle(html_content)
        
        # Add metadata header
        header = f"# {title_text}\n\n"
        header += f"**Source:** {url}\n"
        header += f"**Scraped:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        header += "---\n\n"
        
        return header + markdown_content
    except Exception as e:
        print(f"[ERROR] Failed to convert HTML to Markdown: {e}")
        # Fallback to simple text extraction
        return soup.get_text(separator="\n", strip=True)


def save_content(content, filename):
    """Save content as Markdown file"""
    os.makedirs(DATA_PATH, exist_ok=True)
    filepath = os.path.join(DATA_PATH, f"{filename}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def scrape_content(url):
    """Scrape content from URL (HTML or PDF)"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Could not access {url}: {e}")
        return "", set()
    
    content_type = response.headers.get("Content-Type", "").lower()
    
    # Handle PDF files
    if "application/pdf" in content_type or is_pdf_url(url):
        print(f"[INFO] Processing PDF: {url}")
        pdf_content = extract_pdf_text(response.content)
        if pdf_content:
            # Add source URL to PDF content
            pdf_content = f"# PDF Document\n\n**Source:** {url}\n\n---\n\n" + pdf_content
        return pdf_content, set()
    
    # Handle HTML pages
    elif "text/html" in content_type:
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Extract links for crawling
        links = extract_links(soup, url)
        
        # Convert HTML to Markdown
        markdown_content = html_to_markdown(soup, url)
        
        return markdown_content, links
    
    else:
        print(f"[NOTICE] Unsupported content type at {url} (Content-Type: {content_type}). Skipping.")
        return "", set()


def main():
    index_mapping = {}
    start_time = time.time()
    processed_count = 0
    pdf_count = 0
    
    print(f"[START] Beginning web scraping from {URL_BASE}")
    print("[INFO] Converting content to Markdown format")
    print("[INFO] PDF files will be downloaded and processed")
    print("-" * 50)
    
    while unvisited_urls:
        current_url = unvisited_urls.pop(0)
        
        if current_url in visited_urls:
            continue
        
        print(f"[INFO] Scraping: {current_url}")
        content, links = scrape_content(current_url)
        
        if content:
            filename = clean_filename(current_url)
            save_content(content, filename)
            index_mapping[filename] = current_url
            processed_count += 1
            
            if is_pdf_url(current_url) or "PDF Document" in content[:20]:
                pdf_count += 1
        
        visited_urls.add(current_url)
        
        # Add new links to queue
        new_links = links - visited_urls
        unvisited_urls.extend(new_links - set(unvisited_urls))
        
        # Be respectful with rate limiting
        time.sleep(WAIT_TIME)
    
    # Save URL index
    with open(os.path.join(DATA_PATH, "url_index.json"), "w", encoding="utf-8") as index_file:
        json.dump(index_mapping, index_file, indent=2, ensure_ascii=False)
    
    duration = time.time() - start_time
    print("-" * 50)
    print(f"[END] Scraping completed in {duration:.2f} seconds")
    print(f"[STATS] Total pages processed: {processed_count}")
    print(f"[STATS] PDF files processed: {pdf_count}")
    print(f"[STATS] Total URLs visited: {len(visited_urls)}")


if __name__ == "__main__":
    main()