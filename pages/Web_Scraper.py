import streamlit as st
import requests
from bs4 import BeautifulSoup
from supabase import create_client
import re
from urllib.parse import urljoin

# --- KEYS ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
except:
    st.error("Missing Supabase credentials")
    st.stop()


class ApolloLite:
    def __init__(self, company_name):
        self.company_name = company_name
        self.domain = None
        self.company_id = None

    # ---------------- DOMAIN FINDER ----------------
    def find_domain(self):
        try:
            query = f"{self.company_name} official website"
            url = f"https://www.google.com/search?q={query}"
            headers = {"User-Agent": "Mozilla/5.0"}

            resp = requests.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")

            for a in soup.find_all("a", href=True):
                if "url?q=" in a["href"]:
                    link = a["href"].split("url?q=")[1].split("&")[0]
                    if self.company_name.lower().split()[0] in link:
                        return link
        except:
            pass

        # fallback
        return f"https://{self.company_name.lower().replace(' ', '')}.com"

    # ---------------- MAIN RUN ----------------
    def run(self):
        self.domain = self.find_domain()

        existing = supabase.table("companies").select("id").eq("name", self.company_name).execute()

        if existing.data:
            self.company_id = existing.data[0]["id"]
        else:
            res = supabase.table("companies").insert({
                "name": self.company_name,
                "domain": self.domain
            }).execute()
            self.company_id = res.data[0]["id"]

        paths = [
            "/", "/contact", "/contact-us", "/contactus",
            "/about", "/about-us", "/team",
            "/leadership", "/relations"
        ]

        found = []
        headers = {"User-Agent": "Mozilla/5.0"}

        for path in paths:
            try:
                full_url = urljoin(self.domain, path)
                resp = requests.get(full_url, headers=headers, timeout=10)

                if resp.status_code == 200:
                    found += self.extract_contacts(resp.text, full_url)
            except:
                continue

        # FILTER VALID
        valid = [c for c in found if c.get("email")]

      # DEDUP - Ensure only ONE row per email exists in the batch
        unique = {}
        for c in valid:
            email_key = c['email'].lower().strip()
            
            if email_key not in unique:
                unique[email_key] = c
            else:
                # OPTIONAL: If we find the same email again, 
                # keep the one that has phone numbers
                if not unique[email_key].get("phone_numbers") and c.get("phone_numbers"):
                    unique[email_key] = c

        data = list(unique.values())

        if data:
            supabase.table("contacts").upsert(data, on_conflict="email").execute()

        return data

    # ---------------- EXTRACTION ----------------
    def extract_contacts(self, html, source_url):
        soup = BeautifulSoup(html, "html.parser")

        results = []
        seen_emails = set()

        # ---------------- 1. STRUCTURED EXTRACTION (HIGH PRIORITY) ----------------
        cards = soup.find_all(class_=re.compile("card|profile|team|contact|person", re.I))

        for card in cards:
            name = None
            role = None
            email = None
            phone = None

            # Name
            headings = card.find_all(["h1", "h2", "h3", "h4"])
            if headings:
                name = headings[0].get_text(strip=True)

            # Email
            mail = card.find("a", href=re.compile("mailto:", re.I))
            if mail:
                email = mail["href"].replace("mailto:", "").split("?")[0].strip()

            # Phone
            tel = card.find("a", href=re.compile("tel:", re.I))
            if tel:
                phone = tel["href"].replace("tel:", "").strip()

            # Role (fallback from text)
            text_block = card.get_text(" ", strip=True)
            if name:
                role_text = text_block.replace(name, "").strip()
                role = role_text[:60] if role_text else None

            # Save if valid
            if email and self.is_valid_email(email) and email not in seen_emails:
                seen_emails.add(email)

                results.append({
                    "company_id": self.company_id,
                    "full_name": name or "Unknown",
                    "role": role or "Unknown",
                    "email": email,
                    "phone_numbers": phone,
                    "source_url": source_url,
                    "confidence_score": 90
                })

        # ---------------- 2. GENERIC FALLBACK ----------------
        sections = []

        footer = soup.find("footer")
        if footer:
            sections.append(footer.get_text(" "))

        contact_blocks = soup.find_all(class_=re.compile("contact|footer|address", re.I))
        for block in contact_blocks:
            sections.append(block.get_text(" "))

        sections.append(soup.get_text(" "))
        text = " ".join(sections)

        emails = self.extract_emails(text, soup)
        phones = self.extract_phones(text, soup)

        for email in emails:
            if (
                    self.is_valid_email(email)
                    and email not in seen_emails
            ):
                seen_emails.add(email)

                confidence = self.calculate_confidence(email, phones, source_url)

                results.append({
                    "company_id": self.company_id,
                    "full_name": "General Contact",
                    "role": "Company Office",
                    "email": email,
                    "phone_numbers": ", ".join(phones) if phones else None,
                    "source_url": source_url,
                    "confidence_score": confidence
                })

        return results

    # ---------------- EMAIL ----------------
    def extract_emails(self, text, soup):
        regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = set(re.findall(regex, text))

        for a in soup.find_all("a", href=True):
            if "mailto:" in a["href"]:
                emails.add(a["href"].replace("mailto:", "").split("?")[0])

        return list(emails)

    def is_valid_email(self, email):
        common_providers = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
        domain = self.domain.replace("https://", "").replace("www.", "").split('/')[0]

        is_corporate = domain in email
        is_common = any(p in email for p in common_providers)

        return (is_corporate or is_common) and "noreply" not in email
    # ---------------- PHONE ----------------
    def extract_phones(self, text, soup):
        regex = r'''
        (?:
            \+?\d{1,3}[\s\-]?
        )?
        (?:\(?\d{2,4}\)?[\s\-]?)?
        \d{3,4}[\s\-]?\d{4}
        '''

        raw = re.findall(regex, text, re.VERBOSE)

        for a in soup.find_all("a", href=True):
            if "tel:" in a["href"]:
                raw.append(a["href"].replace("tel:", ""))

        clean = set()

        for num in raw:
            digits = re.sub(r'\D', '', num)
            if 8 <= len(digits) <= 13:
                if digits.startswith("91") and len(digits) == 12:
                    clean.add(f"+91 {digits[2:]}")
                elif len(digits) == 10:
                    clean.add(f"+91 {digits}")
                else:
                    clean.add(digits)

        return list(clean)

    # ---------------- CONFIDENCE ----------------
    def calculate_confidence(self, email, phones, source_url):
        score = 0

        if "contact" in source_url:
            score += 40
        if self.domain.replace("https://", "") in email:
            score += 30
        if phones:
            score += 20
        if "footer" in source_url:
            score += 10

        return min(score, 100)


# ---------------- UI ----------------
st.set_page_config(page_title="ApolloLite MVP", page_icon="🚀")
st.title("🚀 B2B Scraper")

company_name = st.text_input("Company Name", placeholder="e.g. Tesla")

if st.button("Generate Leads"):
    if company_name:
        with st.spinner(f"Scraping {company_name}..."):
            scraper = ApolloLite(company_name)
            results = scraper.run()

            if results:
                st.success(f"Found {len(results)} contacts")
                st.dataframe(results)
            else:
                st.warning("No valid contacts found")
    else:
        st.info("Enter company name")
