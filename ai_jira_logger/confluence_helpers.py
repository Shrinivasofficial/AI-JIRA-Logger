import requests
from bs4 import BeautifulSoup
import os
import google.generativeai as genai

# -----------------------------
# Configure Gemini
# -----------------------------
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
SUMMARIZATION_MODEL = "gemini-2.0-flash"

# -----------------------------
# Confluence config
# -----------------------------
CONFLUENCE_DOMAIN = "https://shrinivassofficial702.atlassian.net/wiki"
CONFLUENCE_EMAIL = os.getenv("JIRA_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("JIRA_API_TOKEN")
auth = (CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
headers = {"Accept": "application/json"}

PROJECT_SPACE_KEY = "~7120204799d197fc51402d94ad0896fc82cd34"
PAGE_FETCH_LIMIT = 200

# -----------------------------
# Global buffers
# -----------------------------
PAGE_CACHE = None
PARAGRAPH_BUFFER = []


# -----------------------------
# Fetch all pages from Confluence
# -----------------------------
def fetch_all_pages():
    url = f"{CONFLUENCE_DOMAIN}/rest/api/content"
    params = {
        "spaceKey": PROJECT_SPACE_KEY,
        "limit": PAGE_FETCH_LIMIT,
        "expand": "body.storage"
    }
    resp = requests.get(url, auth=auth, headers=headers, params=params)
    if resp.status_code != 200:
        print(f"Failed to fetch pages: {resp.text}")
        return {}

    pages = {}
    for result in resp.json().get("results", []):
        page_id = result["id"]
        title = result["title"]
        html_content = result["body"]["storage"]["value"]
        text_content = BeautifulSoup(html_content, "html.parser").get_text(separator="\n")
        pages[title] = {"id": page_id, "text": text_content}
    return pages


# -----------------------------
# Preprocess pages into buffer
# -----------------------------
def build_paragraph_buffer(pages):
    buffer = []
    for title, data in pages.items():
        for para in data["text"].split("\n"):
            para_clean = para.strip()
            if para_clean:
                buffer.append({"title": title, "content": para_clean})
    return buffer


# -----------------------------
# Refresh cache
# -----------------------------
def refresh_cache():
    global PAGE_CACHE, PARAGRAPH_BUFFER
    PAGE_CACHE = fetch_all_pages()
    PARAGRAPH_BUFFER = build_paragraph_buffer(PAGE_CACHE)


# -----------------------------
# Retrieve relevant paragraphs
# -----------------------------
def retrieve_relevant_paragraphs(query, top_n=5):
    query_words = query.lower().split()
    scored = []
    for p in PARAGRAPH_BUFFER:
        score = sum(1 for w in query_words if w in p["content"].lower())
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:top_n]]


# -----------------------------
# Summarize with Gemini
# -----------------------------
def summarize_with_gemini(query, paragraphs):
    context = "\n".join([f"{p['title']}: {p['content']}" for p in paragraphs])
    prompt = f"""
User asked: {query}

Relevant Confluence content:
{context}

Answer clearly, concisely, in plain text. 
If the answer can be directly derived from the content, use the content as-is. 
Do not use markdown or formatting symbols.
"""
    model = genai.GenerativeModel(SUMMARIZATION_MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()


# -----------------------------
# Main API
# -----------------------------
def confluence_answer(query, top_n=5):
    global PAGE_CACHE, PARAGRAPH_BUFFER

    if PAGE_CACHE is None or not PARAGRAPH_BUFFER:
        refresh_cache()

    relevant_paras = retrieve_relevant_paragraphs(query, top_n=top_n)

    if not relevant_paras:
        return "Not sure. This wasn't found in the documentation."

    # If only one clear paragraph matches → return directly
    if len(relevant_paras) == 1:
        return relevant_paras[0]["content"]

    # Otherwise → use Gemini for concise enhancement
    return summarize_with_gemini(query, relevant_paras)
