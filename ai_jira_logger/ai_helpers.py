import google.generativeai as genai
from ai_jira_logger.config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

def enhance_description(raw_text: str) -> str:
    try:
        prompt = (
            "Rewrite the following Jira issue description to be clear, concise, "
            "and professional. Preserve technical details like error codes, logs, "
            "stack traces, and commands exactly as they are.\n\n"
            f"Description:\n{raw_text}"
        )
        resp = gemini_model.generate_content(prompt)
        return resp.text.strip()
    except Exception:
        return raw_text
