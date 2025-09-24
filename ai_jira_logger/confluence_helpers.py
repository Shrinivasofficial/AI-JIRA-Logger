# ai_jira_logger/confluence_helpers.py
import os
from dotenv import load_dotenv
import atlassian
import google.generativeai as genai

# Load environment variables from .env
load_dotenv()

# -------------------------
# Environment variables
# -------------------------
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
SPACE_KEY = os.getenv("SPACE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Validate required variables
if not all([CONFLUENCE_URL, CONFLUENCE_USER, CONFLUENCE_API_TOKEN, SPACE_KEY, GEMINI_API_KEY]):
    raise ValueError("Missing required environment variables for Confluence or Gemini.")

# -------------------------
# Confluence client
# -------------------------
confluence = atlassian.Confluence(
    url=CONFLUENCE_URL,
    username=CONFLUENCE_USER,
    password=CONFLUENCE_API_TOKEN
)

# -------------------------
# Gemini client
# -------------------------
genai.configure(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.0-flash"

# -------------------------
# Cache
# -------------------------
CONFLUENCE_BUFFER = None

def fetch_all_confluence_pages():
    """Fetch all pages from the Confluence space."""
    results = []
    start = 0
    limit = 50
    while True:
        pages = confluence.get_all_pages_from_space(
            space=SPACE_KEY, start=start, limit=limit, expand="body.storage"
        )
        if not pages:
            break
        for page in pages:
            title = page.get("title", "")
            content = page.get("body", {}).get("storage", {}).get("value", "")
            results.append(f"{title}\n\n{content}")
        start += limit
    return results

def refresh_cache():
    """Load Confluence content into memory cache."""
    global CONFLUENCE_BUFFER
    if CONFLUENCE_BUFFER is None:
        pages = fetch_all_confluence_pages()
        CONFLUENCE_BUFFER = "\n\n".join(pages)
    return CONFLUENCE_BUFFER

# Preload cache at startup
refresh_cache()

def confluence_answer(user_query: str) -> str:
    """Generate answer from Confluence content using Gemini."""
    content = refresh_cache()
    
    prompt = f"""
The user asked: "{user_query}"

You are provided with the complete Confluence project documentation below.
Your task is:
1. Find the relevant sections in the content.
2. Answer using ONLY that content. Do not invent any facts.
3. Provide a clear, complete, plain text answer without markdowns or bold unless present in source.

Confluence content:
{content}
"""
    model = genai.GenerativeModel(MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()
