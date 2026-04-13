import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import random
import time
from supabase import create_client

# --- SUPABASE SETUP ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
except Exception:
    st.error("Supabase credentials not found.")

class LinkedInIdentitySource:
    def __init__(self, company_name, company_id):
        self.company_name = company_name
        self.company_id = company_id
        # Rotate User-Agents to mimic different browsers
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ]

    def fetch_identities(self):
        # Broader query: LinkedIn profiles mentioning the company and key roles
        query = f'site:linkedin.com/in/ "{self.company_name}" (CEO OR Founder OR Director OR Manager OR "Head of")'
        search_url = f"https://www.google.com/search?q={query}&num=15"
        
        headers = {
            "User-Agent": random.choice(self.user_agents),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }
        
        identities = []
        try:
            # Added a small sleep to avoid instant bot detection
            time.sleep(random.uniform(1.0, 2.5))
            resp = requests.get(search_url, headers=headers, timeout=15)
            
            if resp.status_code == 200:
                identities = self.parse_google_results(resp.text)
            elif resp.status_code == 429:
                st.error("Google Rate Limit (429) hit. Please wait a few minutes before trying again.")
            else:
                st.error(f"Google Search failed with status: {resp.status_code}")
                
        except Exception as e:
            st.error(f"Request error: {e}")
            
        return identities

    def parse_google_results(self, html):
        soup = BeautifulSoup(html, "html.parser")
        results = []
        
        # 2026 Resilient Selectors: Look for the main result blocks
        # Google often uses div.g or div.MjjYud
        search_blocks = soup.select("div.g") or soup.select("div.MjjYud")
        
        for g in search_blocks:
            title_tag = g.select_one("h3")
            link_tag = g.select_one("a")
            # Snippets are usually in these common classes
            snippet_tag = g.select_one(".VwiC3b") or g.select_one(".kb0B9b")
            
            if title_tag and link_tag:
                raw_title = title_tag.get_text()
                url = link_tag.get('href', '')
                snippet = snippet_tag.get_text() if snippet_tag else ""
                
                # Filter for LinkedIn profile URLs only
                if "linkedin.com/in/" not in url:
                    continue
                
                # Split Title: Usually "Name - Role - Company | LinkedIn"
                parts = re.split(r'[-|]', raw_title)
                name = parts[0].strip()
                
                # Logic to grab role if available
                role = "Professional"
                if len(parts) > 1:
                    role_candidate = parts[1].strip()
                    # Filter out the word 'LinkedIn' if it ends up in the role
                    if "LinkedIn" not in role_candidate:
                        role = role_candidate

                if len(name.split()) >= 2:
                    score = self.calculate_confidence(name, role, snippet)
                    
                    results.append({
                        "company_id": self.company_id,
                        "full_name": name,
                        "role": role,
                        "linkedin_url": url.split("?")[0], # Clean URL
                        "confidence_score": score
                    })
        return results

    def calculate_confidence(self, name, role, snippet):
        score = 10 # Base score for being a valid link
        
        # Check if company name is actually in the snippet or role
        if self.company_name.lower() in snippet.lower() or self.company_name.lower() in role.lower():
            score += 50
        
        # Match high-value keywords
        keywords = ["ceo", "founder", "manager", "head", "director", "owner", "president"]
        if any(kw in role.lower() for kw in keywords):
            score += 30
            
        # LinkedIn formatting check
        if "linkedin.com/in/" in snippet:
            score += 10
            
        return min(score, 100)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Identity Finder", page_icon="👤")
st.title("👤 LinkedIn Identity Finder")
st.markdown("Retrieving key stakeholders via public indexing.")

company_name = st.text_input("Enter Company Name", placeholder="e.g. NVIDIA")

if st.button("Find People"):
    if not company_name:
        st.info("Please enter a company name.")
    else:
        with st.spinner(f"Searching for identities at {company_name}..."):
            # Step 1: Check if company exists
            res = supabase.table("companies").select("id").eq("name", company_name).execute()
            
            if res.data:
                comp_id = res.data[0]['id']
                finder = LinkedInIdentitySource(company_name, comp_id)
                people = finder.fetch_identities()
                
                if people:
                    # Step 3: Upsert (Prevents duplicates by LinkedIn URL)
                    try:
                        supabase.table("linkedin_identities").upsert(people, on_conflict="linkedin_url").execute()
                        st.success(f"Successfully found and saved {len(people)} leads!")
                        
                        # Data visualization
                        st.table([{
                            "Name": p['full_name'],
                            "Role": p['role'],
                            "Confidence": f"{p['confidence_score']}%",
                            "Link": p['linkedin_url']
                        } for p in people])
                    except Exception as e:
                        st.error(f"Database save error: {e}")
                else:
                    st.warning("No identities found. Try a more common company name or wait a moment.")
            else:
                st.error("Company not found. Please run the 'Website Scraper' first to add this company to the database.")
