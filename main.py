import streamlit as st

st.set_page_config(
    page_title="ApolloLite Suite",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 ApolloLite B2B Data Suite")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🌐 Website Scraper")
    st.write("Extract emails and phone numbers directly from company websites.")
    if st.button("Go to Web Scraper"):
        st.switch_page("pages/Web_Scraper.py")

with col2:
    st.subheader("👤 LinkedIn Identity Finder")
    st.write("Identify key decision makers using Google-indexed LinkedIn data.")
    if st.button("Go to Identity Finder"):
        st.switch_page("pages/Identity_Finder.py")

st.info("Select a tool from the sidebar or click a button above to get started.")
