#!/usr/bin/env python3
"""
Test script for the enhanced web scrapper with PDF and Markdown support.
This script demonstrates scraping a few pages to test the functionality.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.rag.scrapper import scrape_content, save_content, clean_filename
import json

def test_scrapper():
    """Test the enhanced scrapper with a limited number of URLs"""
    
    # Test URLs - including the main page and potentially a PDF if found
    test_urls = [
        "https://admision.uandes.cl",
        "https://admision.uandes.cl/carreras",
        "https://admision.uandes.cl/becas"
    ]
    
    print("=" * 60)
    print("ENHANCED WEB SCRAPPER TEST")
    print("=" * 60)
    print("Testing with Markdown formatting and PDF support\n")
    
    results = []
    
    for url in test_urls:
        print(f"\n{'='*60}")
        print(f"Testing URL: {url}")
        print(f"{'='*60}")
        
        try:
            content, links = scrape_content(url)
            
            if content:
                # Save the content
                filename = clean_filename(url)
                save_content(content, filename)
                
                # Get file info
                filepath = os.path.join("data", f"{filename}.md")
                file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                
                # Count markdown elements
                headers = content.count('\n#')
                links_count = content.count('](')
                lists = content.count('\n-') + content.count('\n*') + content.count('\n1.')
                
                result = {
                    "url": url,
                    "filename": f"{filename}.md",
                    "file_size": file_size,
                    "content_length": len(content),
                    "markdown_headers": headers,
                    "markdown_links": links_count,
                    "markdown_lists": lists,
                    "links_found": len(links),
                    "is_pdf": "PDF Document" in content[:50]
                }
                
                results.append(result)
                
                print(f"✅ Success!")
                print(f"   - Saved as: {filename}.md")
                print(f"   - Size: {file_size:,} bytes")
                print(f"   - Content length: {len(content):,} characters")
                print(f"   - Markdown elements: {headers} headers, {links_count} links, {lists} list items")
                print(f"   - Found {len(links)} links to follow")
                
                # Show a preview of the content
                print(f"\n📄 Content Preview (first 500 chars):")
                print("-" * 40)
                print(content[:500])
                print("-" * 40)
                
                # Check for PDF links in the found links
                pdf_links = [link for link in links if link.lower().endswith('.pdf')]
                if pdf_links:
                    print(f"\n📎 Found {len(pdf_links)} PDF links:")
                    for pdf_link in pdf_links[:3]:  # Show first 3
                        print(f"   - {pdf_link}")
                
            else:
                print("❌ No content extracted")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append({
                "url": url,
                "error": str(e)
            })
    
    # Save test results
    with open("test_scrapper_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total URLs tested: {len(test_urls)}")
    print(f"Successful: {len([r for r in results if 'error' not in r])}")
    print(f"Failed: {len([r for r in results if 'error' in r])}")
    print("\nTest results saved to: test_scrapper_results.json")
    print("\nTo run a full scrape, use: python -m app.services.rag.scrapper")

if __name__ == "__main__":
    test_scrapper()