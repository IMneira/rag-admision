#!/usr/bin/env python3
"""
Standalone test for PDF text extraction functionality.
This script tests the PDF extraction without running the full scraper.
"""

import os
import sys
import requests
import io
from pypdf import PdfReader

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.rag.scrapper import extract_pdf_text, save_content, clean_filename

def test_pdf_from_url(pdf_url):
    """Test PDF extraction from a URL"""
    print(f"\n{'='*60}")
    print(f"Testing PDF extraction from URL:")
    print(f"{pdf_url}")
    print(f"{'='*60}")
    
    try:
        # Download the PDF
        print("📥 Downloading PDF...")
        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()
        
        print(f"✅ Downloaded {len(response.content):,} bytes")
        
        # Extract text
        print("🔄 Extracting text...")
        markdown_content = extract_pdf_text(response.content)
        
        if markdown_content:
            print(f"✅ Successfully extracted {len(markdown_content):,} characters")
            
            # Save the extracted content
            filename = clean_filename(pdf_url)
            save_content(markdown_content, f"test_pdf_{filename}")
            
            print(f"💾 Saved as: data/test_pdf_{filename}.md")
            
            # Show preview
            print(f"\n📄 Content Preview (first 1000 chars):")
            print("-" * 60)
            print(markdown_content[:1000])
            print("-" * 60)
            
            # Show stats
            lines = markdown_content.split('\n')
            pages = markdown_content.count('## Page')
            headers = markdown_content.count('\n#')
            
            print(f"\n📊 Extraction Stats:")
            print(f"   - Total characters: {len(markdown_content):,}")
            print(f"   - Total lines: {len(lines):,}")
            print(f"   - Pages detected: {pages}")
            print(f"   - Markdown headers: {headers}")
            
            return True
        else:
            print("❌ No text could be extracted from PDF")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_pdf_from_file(pdf_path):
    """Test PDF extraction from a local file"""
    print(f"\n{'='*60}")
    print(f"Testing PDF extraction from local file:")
    print(f"{pdf_path}")
    print(f"{'='*60}")
    
    try:
        if not os.path.exists(pdf_path):
            print(f"❌ File not found: {pdf_path}")
            return False
        
        # Read the PDF file
        print("📖 Reading PDF file...")
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        print(f"✅ Read {len(pdf_content):,} bytes")
        
        # Extract text
        print("🔄 Extracting text...")
        markdown_content = extract_pdf_text(pdf_content)
        
        if markdown_content:
            print(f"✅ Successfully extracted {len(markdown_content):,} characters")
            
            # Save the extracted content
            filename = os.path.splitext(os.path.basename(pdf_path))[0]
            save_content(markdown_content, f"test_pdf_{filename}")
            
            print(f"💾 Saved as: data/test_pdf_{filename}.md")
            
            # Show preview
            print(f"\n📄 Content Preview (first 1000 chars):")
            print("-" * 60)
            print(markdown_content[:1000])
            print("-" * 60)
            
            return True
        else:
            print("❌ No text could be extracted from PDF")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def create_simple_test():
    """Create a simple text-based test to verify the function works"""
    print(f"\n{'='*60}")
    print("Testing PDF extraction function with minimal example")
    print(f"{'='*60}")
    
    # Create a simple "PDF" content for testing (this won't work with real PDF parsing)
    # But we can test the function structure
    
    try:
        # Test the function exists and can be called
        from app.services.rag.scrapper import extract_pdf_text, html_to_markdown, is_pdf_url
        
        print("✅ Successfully imported PDF extraction functions")
        
        # Test URL detection
        test_urls = [
            "https://formularios.uandes.cl/wp-content/uploads/2019/05/BROCHURE-2019_INTERACTIVO_2.pdf"
        ]
        
        print("\n🔍 Testing PDF URL detection:")
        for url in test_urls:
            is_pdf = is_pdf_url(url)
            print(f"   {url} → {'PDF' if is_pdf else 'Not PDF'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error importing functions: {e}")
        return False

def main():
    """Main test function"""
    print("=" * 80)
    print("PDF TEXT EXTRACTION TEST")
    print("=" * 80)
    
    # Test 1: Function availability
    print("\n1️⃣ Testing function availability...")
    if not create_simple_test():
        print("❌ Basic function test failed!")
        return
    
    # Test 2: Try some known PDF URLs (you can add real URLs here)
    test_pdf_urls = [
        "https://formularios.uandes.cl/wp-content/uploads/2019/05/BROCHURE-2019_INTERACTIVO_2.pdf"
    ]
    
    if test_pdf_urls:
        print(f"\n2️⃣ Testing with {len(test_pdf_urls)} PDF URL(s)...")
        for url in test_pdf_urls:
            test_pdf_from_url(url)
    else:
        print("\n2️⃣ No PDF URLs provided for testing")
    
    # Test 3: Try local PDF files
    print(f"\n3️⃣ Checking for local PDF files...")
    pdf_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, file))
    
    if pdf_files:
        print(f"Found {len(pdf_files)} PDF file(s):")
        for pdf_file in pdf_files[:3]:  # Test max 3 files
            print(f"   - {pdf_file}")
            test_pdf_from_file(pdf_file)
    else:
        print("No local PDF files found for testing")
    
    print(f"\n{'='*80}")
    print("TEST COMPLETE")
    print(f"{'='*80}")
    print("\nTo test with a specific PDF:")
    print("1. Add a PDF URL to the test_pdf_urls list in this script")
    print("2. Place a PDF file in this directory")
    print("3. Or call the functions directly:")
    print("   python -c \"from test_pdf_extraction import test_pdf_from_url; test_pdf_from_url('YOUR_PDF_URL')\"")

if __name__ == "__main__":
    main()