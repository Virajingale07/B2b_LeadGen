import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from supabase import create_client

# Reuse your existing Supabase connection logic
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
except:
    st.error("Supabase credentials not found.")

class LinkedInIdentitySource:
    def __init__(self, company_name, company_id):
        self.company_name = company_name
        self.company_id = company_id
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }

   def fetch_identities(self):
    query = f'site:linkedin.com/in/ "{self.company_name}" (CEO OR Founder OR Director OR Manager)'
    # Use DuckDuckGo HTML search
    search_url = f"https://html.duckduckgo.com/html/?q={query}"
    
    identities = []
    try:
        resp = requests.get(search_url, headers=self.headers, timeout=10)
        
        if resp.status_code == 200:
            identities = self.parse_duckduckgo_results(resp.text)
        else:
            st.error(f"DuckDuckGo returned status: {resp.status_code}")
            
    except Exception as e:
        st.error(f"Search failed: {e}")
        
    return identities

def parse_duckduckgo_results(self, html):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    
    # DuckDuckGo uses different HTML structure
    for results in soup.select(".result"):
        title_tag = result.select_one(".result__a")
        snippet_tag = result.select_one(".result__snippet")
        
        if title_tag:
            url = title_tag.get('href', '')
            raw_title = title_tag.get_text()
            snippet = snippet_tag.get_text() if snippet_tag else ""
            
            if "linkedin.com/in/" not in url:
                continue
            
            # Parse name and role
            parts = raw_title.split("-")
            name = parts[0].replace("| LinkedIn", "").strip()
            role = parts[1].strip() if len(parts) > 1 else "Professional"
            
            if len(name.split()) >= 2:
                score = self.calculate_confidence(name, role, snippet)
                
                results.append({
                    "company_id": self.company_id,
                    "full_name": name,
                    "role": role,
                    "linkedin_url": url.split("?")[0],
                    "confidence_score": score
                })
    
    return results

    def calculate_confidence(self, name, role, snippet):
        score = 0
        if self.company_name.lower() in snippet.lower():
            score += 50
        if any(kw in role.lower() for kw in ["manager", "head", "director", "ceo", "founder","Operations Manager"]):
            score += 30
        if "linkedin.com/in/" in snippet or "linkedin.com/in/" in name: # Placeholder for URL check
            score += 20
        return min(score, 100)

# --- STREAMLIT UI ---
st.title("👤 LinkedIn Identity Finder")
st.markdown("Finds key stakeholders via public Google indexing. No direct LinkedIn scraping.")

# We assume the company already exists in your 'companies' table
company_name = st.text_input("Enter Company Name to Identify Staff", placeholder="e.g. NVIDIA")

if st.button("Find People"):
    if company_name:
        with st.spinner(f"Searching for identities at {company_name}..."):
            # Step 1: Get/Create company_id from your existing table
            # (Reusing your logic from the previous scraper)
            res = supabase.table("companies").select("id").eq("name", company_name).execute()
            
            if res.data:
                comp_id = res.data[0]['id']
                
                # Step 2: Run Identity Search
                finder = LinkedInIdentitySource(company_name, comp_id)
                people = finder.fetch_identities()
                
                if people:
                    # Step 3: Upsert to Supabase
                    supabase.table("linkedin_identities").upsert(people, on_conflict="linkedin_url").execute()
                    
                    st.success(f"Found {len(people)} identities!")
                    
                    # Displaying results
                    display_data = []
                    for p in people:
                        display_data.append({
                            "Name": p['full_name'],
                            "Role": p['role'],
                            "LinkedIn": p['linkedin_url'],
                            "Confidence": f"{p['confidence_score']}%"
                        })
                    st.table(display_data)
                else:
                    st.warning("No identities found. Google might be rate-limiting or the query is too specific.")
            else:
                st.error("Company not found in main database. Please run the Website Scraper first.")
