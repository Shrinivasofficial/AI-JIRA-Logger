import os
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")  # Jira bot/admin account
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")  # e.g. https://your-domain.atlassian.net
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def validate_config():
    if not all([SLACK_BOT_TOKEN, JIRA_API_TOKEN, JIRA_EMAIL, JIRA_DOMAIN, GEMINI_API_KEY]):
        raise RuntimeError("❌ Missing required environment variables")
