import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import random
import time
from supabase import create_client
from urllib.parse import quote_plus, unquote

# --- SUPABASE SETUP ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
except Exception as e:
    st.error(f"Supabase credentials not found: {e}")
    supabase = None

class LinkedInIdentitySource:
    def __init__(self, company_name, company_id, search_engine="duckduckgo"):
        self.company_name = company_name
        self.company_id = company_id
        self.search_engine = search_engine
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
        ]

    def fetch_identities(self):
        if self.search_engine == "duckduckgo":
            return self.fetch_from_duckduckgo()
        else:
            return self.fetch_from_google()

    def fetch_from_duckduckgo(self):
        """DuckDuckGo is more scraping-friendly than Google"""
        # Search for LinkedIn profiles
        query = f'site:linkedin.com/in/ "{self.company_name}" (CEO OR Founder OR Director OR Manager)'
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        
        headers = {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        identities = []
        try:
            time.sleep(random.uniform(1.5, 3.0))
            
            st.info(f"🔍 Searching DuckDuckGo for LinkedIn profiles...")
            resp = requests.get(search_url, headers=headers, timeout=20)
            
            st.write(f"📡 Response Status: {resp.status_code}")
            st.write(f"📄 HTML Response Length: {len(resp.text)} characters")
            
            if resp.status_code == 200:
                identities = self.parse_duckduckgo_results(resp.text)
            else:
                st.error(f"❌ Search failed with status: {resp.status_code}")
                
        except requests.exceptions.Timeout:
            st.error("⏱️ Request timed out. Please try again.")
        except Exception as e:
            st.error(f"❌ Error: {e}")
            
        return identities

    def parse_duckduckgo_results(self, html):
        soup = BeautifulSoup(html, "html.parser")
        results = []
        
        # DuckDuckGo uses consistent class names
        search_results = soup.find_all('div', class_='result')
        
        st.write(f"🔎 Found {len(search_results)} search results")
        
        if len(search_results) == 0:
            st.warning("⚠️ No results found from DuckDuckGo")
            with st.expander("🔧 Debug: View HTML Sample"):
                st.code(html[:2000], language="html")
            return []
        
        for idx, result in enumerate(search_results):
            try:
                # Get the title link
                title_link = result.find('a', class_='result__a')
                if not title_link:
                    continue
                
                url = title_link.get('href', '')
                title_text = title_link.get_text(strip=True)
                
                # Get snippet
                snippet_elem = result.find('a', class_='result__snippet')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                
                # Filter for LinkedIn profiles only
                if 'linkedin.com/in/' not in url:
                    continue
                
                # Clean URL
                url = unquote(url)
                
                if idx < 3:
                    st.write(f"✅ Result {idx+1}: {title_text[:60]}...")
                
                # Parse name and role from title
                # DuckDuckGo format: "Name - Role - Company | LinkedIn"
                name, role = self.parse_title(title_text, snippet)
                
                if name and len(name.split()) >= 2:
                    score = self.calculate_confidence(name, role, snippet)
                    
                    results.append({
                        "company_id": self.company_id,
                        "full_name": name,
                        "role": role,
                        "linkedin_url": url.split("?")[0],
                        "confidence_score": score
                    })
                    
            except Exception as e:
                st.warning(f"⚠️ Error parsing result {idx}: {e}")
                continue
        
        st.write(f"✅ Successfully parsed {len(results)} valid identities")
        return results

    def fetch_from_google(self):
        """Fallback to Google (more likely to be blocked)"""
        query = f'site:linkedin.com/in/ "{self.company_name}" (CEO OR Founder OR Director OR Manager)'
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&num=20"
        
        headers = {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.google.com/"
        }
        
        identities = []
        try:
            time.sleep(random.uniform(2.0, 4.0))
            
            st.info(f"🔍 Searching Google for LinkedIn profiles...")
            resp = requests.get(search_url, headers=headers, timeout=20)
            
            st.write(f"📡 Response Status: {resp.status_code}")
            st.write(f"📄 HTML Response Length: {len(resp.text)} characters")
            
            if resp.status_code == 200:
                # Check for blocking
                if any(keyword in resp.text.lower() for keyword in ["captcha", "unusual traffic", "detected unusual", "not a robot"]):
                    st.error("🚫 Google CAPTCHA detected - switching to DuckDuckGo...")
                    with st.expander("🔧 Debug: View blocked page"):
                        st.code(resp.text[:1000], language="html")
                    return []
                
                identities = self.parse_google_results(resp.text)
            else:
                st.error(f"❌ Google returned status: {resp.status_code}")
                
        except Exception as e:
            st.error(f"❌ Google search error: {e}")
            
        return identities

    def parse_google_results(self, html):
        soup = BeautifulSoup(html, "html.parser")
        results = []
        
        # Try multiple selectors
        search_blocks = (
            soup.select("div.g") or 
            soup.select("div.MjjYud") or 
            soup.select("div.Gx5Zad") or
            soup.select("div[data-sokoban-container]")
        )
        
        st.write(f"🔎 Found {len(search_blocks)} Google search blocks")
        
        if len(search_blocks) == 0:
            # Try finding any LinkedIn links as fallback
            all_links = soup.find_all('a', href=re.compile(r'linkedin\.com/in/'))
            st.write(f"🔗 Fallback: Found {len(all_links)} LinkedIn links")
            
            for link in all_links[:20]:
                url = link.get('href', '')
                if '/url?q=' in url:
                    url = url.split('/url?q=')[1].split('&')[0]
                
                if 'linkedin.com/in/' in url:
                    text = link.get_text(strip=True)
                    name, role = self.parse_title(text, "")
                    
                    if name and len(name.split()) >= 2:
                        results.append({
                            "company_id": self.company_id,
                            "full_name": name,
                            "role": role,
                            "linkedin_url": url.split("?")[0],
                            "confidence_score": 30
                        })
            return results
        
        for g in search_blocks:
            title_tag = g.select_one("h3")
            link_tag = g.select_one("a")
            snippet_tag = g.select_one(".VwiC3b") or g.select_one(".IsZvec")
            
            if title_tag and link_tag:
                url = link_tag.get('href', '')
                if '/url?q=' in url:
                    url = url.split('/url?q=')[1].split('&')[0]
                
                if 'linkedin.com/in/' not in url:
                    continue
                
                title_text = title_tag.get_text(strip=True)
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                
                name, role = self.parse_title(title_text, snippet)
                
                if name and len(name.split()) >= 2:
                    score = self.calculate_confidence(name, role, snippet)
                    results.append({
                        "company_id": self.company_id,
                        "full_name": name,
                        "role": role,
                        "linkedin_url": url.split("?")[0],
                        "confidence_score": score
                    })
        
        return results

    def parse_title(self, title_text, snippet):
        """Extract name and role from title"""
        # Remove LinkedIn suffix
        title_text = re.sub(r'\s*[|•]\s*LinkedIn.*$', '', title_text, flags=re.IGNORECASE)
        
        # Split by common separators
        parts = re.split(r'[-–—|•]', title_text)
        
        name = parts[0].strip() if parts else "Unknown"
        role = "Professional"
        
        if len(parts) > 1:
            role_candidate = parts[1].strip()
            if role_candidate and len(role_candidate) > 2 and "LinkedIn" not in role_candidate:
                role = role_candidate
        
        # Try to extract role from snippet if not found
        if role == "Professional" and snippet:
            role_patterns = [
                r'(CEO|CTO|CFO|COO|CMO)\b',
                r'(Chief [A-Z][a-z]+ Officer)',
                r'(Co-?Founder|Founder)\b',
                r'(Director|Manager|Head of [^.,:]+)',
                r'(President|Vice President|VP)\b',
            ]
            for pattern in role_patterns:
                match = re.search(pattern, snippet, re.IGNORECASE)
                if match:
                    role = match.group(1).strip()
                    break
        
        return name, role

    def calculate_confidence(self, name, role, snippet):
        score = 10
        
        if self.company_name.lower() in snippet.lower():
            score += 40
        if self.company_name.lower() in role.lower():
            score += 20
        
        high_value = ["ceo", "founder", "co-founder", "president", "owner", "chief"]
        mid_value = ["director", "head of", "manager", "vp", "vice president"]
        
        role_lower = role.lower()
        if any(kw in role_lower for kw in high_value):
            score += 30
        elif any(kw in role_lower for kw in mid_value):
            score += 20
        
        name_parts = name.split()
        if len(name_parts) >= 2 and all(len(p) > 1 for p in name_parts[:2]):
            score += 10
            
        return min(score, 100)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Identity Finder", page_icon="👤")
st.title("👤 LinkedIn Identity Finder")
st.markdown("Retrieving key stakeholders via public indexing.")

# Search Engine Selection
search_engine = st.radio(
    "Select Search Engine:",
    ["DuckDuckGo (Recommended)", "Google (May be blocked)"],
    index=0
)

engine_key = "duckduckgo" if "DuckDuckGo" in search_engine else "google"

company_name = st.text_input("Enter Company Name", placeholder="e.g. NVIDIA")

col1, col2 = st.columns([3, 1])
with col1:
    st.info("💡 **Tip**: Use the full company name as it appears on LinkedIn")
with col2:
    debug_mode = st.checkbox("🐛 Debug", value=False)

if st.button("🔍 Find People", type="primary"):
    if not company_name:
        st.warning("⚠️ Please enter a company name.")
    elif not supabase:
        st.error("❌ Supabase is not configured.")
    else:
        with st.spinner(f"Searching for identities at {company_name}..."):
            try:
                # Check if company exists
                st.write("📊 Checking company in database...")
                res = supabase.table("companies").select("id, name").eq("name", company_name).execute()
                
                if debug_mode:
                    st.json({"database_response": res.data})
                
                if res.data:
                    comp_id = res.data[0]['id']
                    st.success(f"✅ Company found: {res.data[0]['name']}")
                    
                    # Search for identities
                    finder = LinkedInIdentitySource(company_name, comp_id, engine_key)
                    people = finder.fetch_identities()
                    
                    if people:
                        st.write(f"💾 Saving {len(people)} profiles to database...")
                        
                        try:
                            supabase.table("linkedin_identities").upsert(
                                people, 
                                on_conflict="linkedin_url"
                            ).execute()
                            
                            st.success(f"🎉 Found and saved {len(people)} leads!")
                            
                            # Display results
                            people_sorted = sorted(people, key=lambda x: x['confidence_score'], reverse=True)
                            
                            st.subheader("📊 Results")
                            
                            for p in people_sorted:
                                with st.container():
                                    col1, col2, col3 = st.columns([3, 2, 1])
                                    with col1:
                                        st.markdown(f"**{p['full_name']}**")
                                        st.caption(p['role'])
                                    with col2:
                                        st.link_button("View Profile", p['linkedin_url'], use_container_width=True)
                                    with col3:
                                        score_color = "🟢" if p['confidence_score'] >= 70 else "🟡" if p['confidence_score'] >= 40 else "🔴"
                                        st.metric("Score", f"{score_color} {p['confidence_score']}")
                            
                            # Download CSV
                            csv_data = "Name,Role,Confidence,LinkedIn URL\n"
                            csv_data += "\n".join([
                                f'"{p["full_name"]}","{p["role"]}",{p["confidence_score"]},{p["linkedin_url"]}'
                                for p in people_sorted
                            ])
                            
                            st.download_button(
                                label="📥 Download CSV",
                                data=csv_data,
                                file_name=f"{company_name.replace(' ', '_')}_leads.csv",
                                mime="text/csv"
                            )
                            
                        except Exception as e:
                            st.error(f"❌ Database error: {e}")
                    else:
                        st.warning("⚠️ No profiles found")
                        st.markdown("""
                        **Suggestions:**
                        - Try the full legal company name
                        - Switch search engines (toggle above)
                        - Wait a few minutes and try again
                        - Check if the company has public LinkedIn presence
                        """)
                else:
                    st.error(f"❌ Company not found: '{company_name}'")
                    
                    if st.button("➕ Add Company & Retry"):
                        try:
                            supabase.table("companies").insert({"name": company_name}).execute()
                            st.success("✅ Company added! Click 'Find People' again.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")
                            
            except Exception as e:
                st.error(f"❌ Error: {e}")
                if debug_mode:
                    st.exception(e)

st.markdown("---")
st.caption("⚠️ Use responsibly. Respect rate limits and privacy.")
