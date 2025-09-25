import google.generativeai as genai
from ai_jira_logger.config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

def enhance_description(raw_text: str) -> str:
    try:
        prompt = f"""
        Take the following input text and rewrite it into a professional Jira ticket description.
        Include:
        - A concise Summary (1 line)
        - A clear Description (2-4 lines)

        Do not provide multiple options, explanations, or meta-comments.
        Just return the final formatted Jira text.
        The formatting should be clean without any markdowns or ***.
        Input: "{raw_text}"
        """
        resp = gemini_model.generate_content(prompt)
        return resp.text.strip()
    except Exception:
        return raw_text
