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
except Exception as e:
    st.error(f"Supabase credentials not found: {e}")
    supabase = None

class LinkedInIdentitySource:
    def __init__(self, company_name, company_id):
        self.company_name = company_name
        self.company_id = company_id
        # Rotate User-Agents to mimic different browsers
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
        ]

    def fetch_identities(self):
        # Broader query: LinkedIn profiles mentioning the company and key roles
        query = f'site:linkedin.com/in/ "{self.company_name}" (CEO OR Founder OR Director OR Manager OR "Head of")'
        search_url = f"https://www.google.com/search?q={query}&num=20"
        
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
            # Sleep to avoid instant bot detection
            time.sleep(random.uniform(2.0, 4.0))
            
            st.info(f"🔍 Searching Google for: {query[:100]}...")
            resp = requests.get(search_url, headers=headers, timeout=20)
            
            st.write(f"📡 Response Status: {resp.status_code}")
            
            if resp.status_code == 200:
                # Check for CAPTCHA or blocking
                if "captcha" in resp.text.lower() or "unusual traffic" in resp.text.lower():
                    st.error("🚫 Google detected automated queries (CAPTCHA page received)")
                    st.warning("💡 Try again in a few minutes or use a VPN")
                    return []
                
                st.write(f"📄 HTML Response Length: {len(resp.text)} characters")
                identities = self.parse_google_results(resp.text)
                
            elif resp.status_code == 429:
                st.error("⚠️ Google Rate Limit (429) hit. Please wait 5-10 minutes before trying again.")
            else:
                st.error(f"❌ Google Search failed with status: {resp.status_code}")
                
        except requests.exceptions.Timeout:
            st.error("⏱️ Request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
            st.error(f"🌐 Network error: {e}")
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")
            
        return identities

    def parse_google_results(self, html):
        soup = BeautifulSoup(html, "html.parser")
        results = []
        
        # Multiple selector strategies for resilience
        search_blocks = (
            soup.select("div.g") or 
            soup.select("div.MjjYud") or 
            soup.select("div.Gx5Zad") or
            soup.select("div[data-sokoban-container]")
        )
        
        st.write(f"🔎 Found {len(search_blocks)} search result blocks")
        
        if len(search_blocks) == 0:
            st.warning("⚠️ No search blocks found - Google may have changed their HTML structure")
            st.expander("🔧 Debug: View HTML Sample").code(html[:2000], language="html")
            
            # Fallback: Try to find any LinkedIn links
            all_links = soup.find_all('a', href=re.compile(r'linkedin\.com/in/'))
            st.write(f"🔗 Fallback: Found {len(all_links)} LinkedIn links in page")
            
            if all_links:
                for link in all_links[:15]:
                    url = link.get('href', '')
                    # Clean Google redirect URL
                    if '/url?q=' in url:
                        url = url.split('/url?q=')[1].split('&')[0]
                    
                    if 'linkedin.com/in/' in url:
                        # Try to extract name from link text or nearby text
                        name = link.get_text(strip=True)
                        if not name or len(name) < 3:
                            # Look for h3 near this link
                            h3 = link.find_parent().find('h3') if link.find_parent() else None
                            name = h3.get_text(strip=True) if h3 else "Unknown"
                        
                        if len(name.split()) >= 2:
                            results.append({
                                "company_id": self.company_id,
                                "full_name": name.split('-')[0].strip() if '-' in name else name,
                                "role": "Professional",
                                "linkedin_url": url.split("?")[0],
                                "confidence_score": 40
                            })
            
            return results
        
        for idx, g in enumerate(search_blocks):
            try:
                # Multiple selector strategies for title
                title_tag = (
                    g.select_one("h3") or 
                    g.select_one("h3.LC20lb") or
                    g.select_one("div[role='heading']")
                )
                
                # Multiple selector strategies for link
                link_tag = g.select_one("a")
                
                # Multiple selector strategies for snippet
                snippet_tag = (
                    g.select_one(".VwiC3b") or 
                    g.select_one(".kb0B9b") or
                    g.select_one(".yXK7lf") or
                    g.select_one("div[data-content-feature='1']") or
                    g.select_one(".IsZvec")
                )
                
                if not (title_tag and link_tag):
                    continue
                
                raw_title = title_tag.get_text(strip=True)
                url = link_tag.get('href', '')
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                
                # Clean Google redirect URLs
                if '/url?q=' in url:
                    url = url.split('/url?q=')[1].split('&')[0]
                
                # Filter for LinkedIn profile URLs only
                if "linkedin.com/in/" not in url:
                    continue
                
                # Debug first few results
                if idx < 3:
                    st.write(f"✅ Result {idx+1}: {raw_title[:50]}...")
                
                # Split Title: Usually "Name - Role - Company | LinkedIn"
                parts = re.split(r'[-|–—]', raw_title)
                name = parts[0].strip()
                
                # Remove common LinkedIn suffixes
                name = re.sub(r'\s*\|\s*LinkedIn.*$', '', name, flags=re.IGNORECASE)
                
                # Logic to grab role if available
                role = "Professional"
                if len(parts) > 1:
                    role_candidate = parts[1].strip()
                    # Filter out the word 'LinkedIn' if it ends up in the role
                    if "LinkedIn" not in role_candidate and len(role_candidate) > 2:
                        role = role_candidate
                
                # Extract role from snippet if not found in title
                if role == "Professional" and snippet:
                    # Look for role patterns in snippet
                    role_patterns = [
                        r'(CEO|CTO|CFO|COO|Director|Manager|Head of [^.]+|Founder|President|VP)',
                        r'(Chief [^.]+Officer)',
                    ]
                    for pattern in role_patterns:
                        match = re.search(pattern, snippet, re.IGNORECASE)
                        if match:
                            role = match.group(1)
                            break
                
                # Validate name (must have at least 2 parts and reasonable length)
                if len(name.split()) >= 2 and len(name) < 100:
                    score = self.calculate_confidence(name, role, snippet)
                    
                    results.append({
                        "company_id": self.company_id,
                        "full_name": name,
                        "role": role,
                        "linkedin_url": url.split("?")[0],  # Clean URL
                        "confidence_score": score
                    })
                    
            except Exception as e:
                st.warning(f"⚠️ Error parsing result {idx}: {e}")
                continue
        
        st.write(f"✅ Successfully parsed {len(results)} valid identities")
        return results

    def calculate_confidence(self, name, role, snippet):
        score = 10  # Base score for being a valid link
        
        # Check if company name is actually in the snippet or role
        if self.company_name.lower() in snippet.lower():
            score += 40
        if self.company_name.lower() in role.lower():
            score += 20
        
        # Match high-value keywords
        high_value_keywords = ["ceo", "founder", "co-founder", "president", "owner"]
        mid_value_keywords = ["director", "head of", "manager", "vp", "vice president", "cto", "cfo", "coo"]
        
        role_lower = role.lower()
        if any(kw in role_lower for kw in high_value_keywords):
            score += 30
        elif any(kw in role_lower for kw in mid_value_keywords):
            score += 20
            
        # LinkedIn formatting check
        if "linkedin.com/in/" in snippet.lower():
            score += 10
        
        # Name quality check
        name_parts = name.split()
        if len(name_parts) >= 2 and all(len(part) > 1 for part in name_parts[:2]):
            score += 10
            
        return min(score, 100)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Identity Finder", page_icon="👤")
st.title("👤 LinkedIn Identity Finder")
st.markdown("Retrieving key stakeholders via public indexing.")

st.info("⚠️ **Note**: Google may block automated searches. If you get no results, wait a few minutes and try again.")

company_name = st.text_input("Enter Company Name", placeholder="e.g. NVIDIA")

# Optional: Debug mode
debug_mode = st.checkbox("🐛 Enable Debug Mode", value=False)

if st.button("🔍 Find People"):
    if not company_name:
        st.warning("⚠️ Please enter a company name.")
    elif not supabase:
        st.error("❌ Supabase is not configured. Check your secrets.")
    else:
        with st.spinner(f"Searching for identities at {company_name}..."):
            try:
                # Step 1: Check if company exists
                st.write("📊 Step 1: Checking company in database...")
                res = supabase.table("companies").select("id, name").eq("name", company_name).execute()
                
                if debug_mode:
                    st.write("Database Response:", res.data)
                
                if res.data:
                    comp_id = res.data[0]['id']
                    st.success(f"✅ Found company: {res.data[0]['name']} (ID: {comp_id})")
                    
                    # Step 2: Search for identities
                    st.write("🔎 Step 2: Searching Google for LinkedIn profiles...")
                    finder = LinkedInIdentitySource(company_name, comp_id)
                    people = finder.fetch_identities()
                    
                    if people:
                        st.write(f"📋 Step 3: Saving {len(people)} identities to database...")
                        
                        # Step 3: Upsert (Prevents duplicates by LinkedIn URL)
                        try:
                            result = supabase.table("linkedin_identities").upsert(
                                people, 
                                on_conflict="linkedin_url"
                            ).execute()
                            
                            st.success(f"🎉 Successfully found and saved {len(people)} leads!")
                            
                            # Sort by confidence score
                            people_sorted = sorted(people, key=lambda x: x['confidence_score'], reverse=True)
                            
                            # Data visualization
                            st.subheader("📊 Found Identities")
                            
                            display_data = []
                            for p in people_sorted:
                                display_data.append({
                                    "Name": p['full_name'],
                                    "Role": p['role'],
                                    "Confidence": f"{p['confidence_score']}%",
                                    "LinkedIn": p['linkedin_url']
                                })
                            
                            st.dataframe(display_data, use_container_width=True)
                            
                            # Download option
                            st.download_button(
                                label="📥 Download Results as CSV",
                                data="\n".join([f"{p['full_name']},{p['role']},{p['confidence_score']},{p['linkedin_url']}" for p in people_sorted]),
                                file_name=f"{company_name}_linkedin_leads.csv",
                                mime="text/csv"
                            )
                            
                        except Exception as e:
                            st.error(f"❌ Database save error: {e}")
                            if debug_mode:
                                st.exception(e)
                    else:
                        st.warning("⚠️ No identities found. Possible reasons:")
                        st.markdown("""
                        - Google may be blocking automated searches (try again in 5-10 minutes)
                        - The company name might not have public LinkedIn profiles indexed
                        - Try using a more specific or well-known company name
                        - Google's HTML structure may have changed (enable Debug Mode to investigate)
                        """)
                else:
                    st.error(f"❌ Company '{company_name}' not found in database.")
                    st.info("💡 Please run the 'Website Scraper' first to add this company to the database.")
                    
                    # Optionally, auto-create the company
                    if st.button("➕ Add Company to Database Now"):
                        try:
                            new_company = supabase.table("companies").insert({
                                "name": company_name
                            }).execute()
                            st.success(f"✅ Added '{company_name}' to database! Now click 'Find People' again.")
                        except Exception as e:
                            st.error(f"Failed to add company: {e}")
                            
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")
                if debug_mode:
                    st.exception(e)

# Footer
st.markdown("---")
st.caption("⚠️ This tool uses public Google search. Use responsibly and respect rate limits.")
