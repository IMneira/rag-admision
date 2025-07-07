#!/usr/bin/env python3
"""
Test script for the new database health and PDF count endpoints
"""

import requests
import json
from getpass import getpass

def test_database_endpoints():
    """Test the database health and PDF count endpoints"""
    
    # Configuration
    base_url = "http://localhost:5000"
    
    print("=== Testing Database Health and PDF Count Endpoints ===")
    
    # Get admin credentials
    print("\nAdmin login required for testing:")
    username = input("Username: ")
    password = getpass("Password: ")
    
    # Create session
    session = requests.Session()
    
    # Login
    print(f"\n1. Logging in as {username}...")
    login_data = {
        'username': username,
        'password': password
    }
    
    try:
        login_response = session.post(f"{base_url}/login", data=login_data)
        if login_response.status_code == 200:
            print("✅ Login successful")
        else:
            print(f"❌ Login failed: {login_response.status_code}")
            return
    except Exception as e:
        print(f"❌ Login error: {e}")
        return
    
    # Test database health endpoint
    print("\n2. Testing /api/database/health endpoint...")
    try:
        health_response = session.get(f"{base_url}/api/database/health")
        if health_response.status_code == 200:
            print("✅ Database health endpoint accessible")
            health_data = health_response.json()
            
            print(f"   Overall Status: {health_data['data']['overall_status']}")
            print(f"   Error Count: {health_data['data']['error_count']}")
            
            # Print system statuses
            for system, status in health_data['data']['summary'].items():
                status_icon = "✅" if status else "❌"
                print(f"   {system}: {status_icon}")
                
            # Show detailed stats
            print("\n   Detailed Statistics:")
            systems = health_data['data']['systems']
            
            if systems['sqlite']['status'] == 'healthy':
                sqlite_data = systems['sqlite']
                print(f"   SQLite: {sqlite_data['conversations']} conversations, {sqlite_data['messages']} messages, {sqlite_data['users']} users")
            
            if systems['vector_db']['status'] == 'healthy':
                vector_data = systems['vector_db']
                print(f"   Vector DB: {vector_data['total_chunks']} chunks, {vector_data['unique_documents']} documents")
            
        else:
            print(f"❌ Database health endpoint failed: {health_response.status_code}")
            print(f"   Response: {health_response.text}")
            
    except Exception as e:
        print(f"❌ Database health endpoint error: {e}")
    
    # Test PDF count endpoint
    print("\n3. Testing /api/database/pdf-count endpoint...")
    try:
        pdf_response = session.get(f"{base_url}/api/database/pdf-count")
        if pdf_response.status_code == 200:
            print("✅ PDF count endpoint accessible")
            pdf_data = pdf_response.json()
            
            summary = pdf_data['data']['summary']
            print(f"   Total PDFs: {summary['total_pdfs']}")
            print(f"   Uploaded: {summary['uploaded_vs_scraped']['uploaded']}")
            print(f"   Scraped: {summary['uploaded_vs_scraped']['scraped']}")
            print(f"   Recent (24h): {summary['recent_activity']['last_24h']}")
            print(f"   Recent (7d): {summary['recent_activity']['last_week']}")
            
            # Show some PDF sources if available
            pdf_sources = pdf_data['data']['pdf_statistics']['pdf_sources']
            if pdf_sources:
                print(f"\n   Sample PDF Sources (first 3):")
                for i, source in enumerate(pdf_sources[:3]):
                    print(f"   {i+1}. {source['type']}: {source['original_source'][:60]}...")
            
        else:
            print(f"❌ PDF count endpoint failed: {pdf_response.status_code}")
            print(f"   Response: {pdf_response.text}")
            
    except Exception as e:
        print(f"❌ PDF count endpoint error: {e}")
    
    # Test API info endpoint to verify new endpoints are listed
    print("\n4. Testing /api/info endpoint for new endpoints...")
    try:
        info_response = session.get(f"{base_url}/api/info")
        if info_response.status_code == 200:
            info_data = info_response.json()
            endpoints = info_data['data']['endpoints']
            
            # Check if our new endpoints are listed
            health_endpoint = any(ep['path'] == '/api/database/health' for ep in endpoints)
            pdf_endpoint = any(ep['path'] == '/api/database/pdf-count' for ep in endpoints)
            
            print(f"   Health endpoint in info: {'✅' if health_endpoint else '❌'}")
            print(f"   PDF count endpoint in info: {'✅' if pdf_endpoint else '❌'}")
            
        else:
            print(f"❌ API info endpoint failed: {info_response.status_code}")
            
    except Exception as e:
        print(f"❌ API info endpoint error: {e}")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_database_endpoints()