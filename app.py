import os
import requests
import logging
from fastapi import FastAPI, Request
from slack_sdk import WebClient
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from datetime import datetime

# -----------------------
# Setup
# -----------------------
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")  # Jira bot/admin account
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")  # e.g. https://your-domain.atlassian.net

if not all([SLACK_BOT_TOKEN, JIRA_API_TOKEN, JIRA_EMAIL, JIRA_DOMAIN]):
    raise RuntimeError("❌ Missing required environment variables")

slack_client = WebClient(token=SLACK_BOT_TOKEN)
app = FastAPI()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -----------------------
# Jira Helpers
# -----------------------
def log_to_jira_worklog(issue_key: str, message: str, time_spent: str = "30m"):
    """Log work into Jira issue"""
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/worklog"
    payload = {
        "comment": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"text": message, "type": "text"}]}],
        },
        "timeSpent": time_spent,
        "started": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
    }

    resp = requests.post(
        url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Content-Type": "application/json"},
        json=payload,
    )
    logging.info(f"Worklog response: {resp.status_code}")
    return resp.status_code, resp.text


def fetch_user_tickets(jira_email: str):
    """Fetch Jira tickets assigned to user"""
    url = f"{JIRA_DOMAIN}/rest/api/3/search"
    jql = f'assignee = "{jira_email}" AND resolution = Unresolved ORDER BY updated DESC'

    resp = requests.get(
        url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Content-Type": "application/json"},
        params={"jql": jql, "maxResults": 5},
    )

    if resp.status_code == 200:
        issues = resp.json().get("issues", [])
        return [(issue["key"], issue["fields"]["summary"]) for issue in issues]
    else:
        logging.error(f"Failed to fetch tickets: {resp.text}")
        return []


def update_issue_description(issue_key: str, new_text: str):
    """Append to Jira issue description"""
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}?fields=description"
    resp = requests.get(
        url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
    )

    if resp.status_code != 200:
        return resp.status_code, f"Failed to fetch description: {resp.text}"

    data = resp.json()
    current_desc = ""
    try:
        content = data["fields"]["description"]["content"]
        current_desc = "\n".join(
            "".join(part.get("text", "") for part in block.get("content", []))
            for block in content
        )
    except Exception:
        current_desc = ""

    updated_desc = (current_desc + "\n" + new_text).strip()

    update_url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}"
    payload = {
        "fields": {
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"text": updated_desc, "type": "text"}]}],
            }
        }
    }

    put_resp = requests.put(
        update_url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Content-Type": "application/json"},
        json=payload,
    )
    return put_resp.status_code, put_resp.text


# -----------------------
# Slack Helpers
# -----------------------
def get_slack_user_email(user_id: str):
    """Get Slack user email by ID"""
    try:
        resp = slack_client.users_info(user=user_id)
        if resp["ok"]:
            return resp["user"]["profile"].get("email")
    except Exception as e:
        logging.error(f"Slack API error: {e}")
    return None

def fetch_user_tickets_with_subtasks(jira_email: str):
    """Fetch Jira tickets + subtasks assigned to user"""
    url = f"{JIRA_DOMAIN}/rest/api/3/search"
    jql = f'assignee = "{jira_email}" AND resolution = Unresolved ORDER BY updated DESC'

    resp = requests.get(
        url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Content-Type": "application/json"},
        params={"jql": jql, "maxResults": 5, "fields": "summary,subtasks"},
    )

    if resp.status_code == 200:
        issues = resp.json().get("issues", [])
        results = []
        for issue in issues:
            issue_key = issue["key"]
            summary = issue["fields"]["summary"]
            results.append((issue_key, summary, "parent"))

            # include subtasks
            for sub in issue["fields"].get("subtasks", []):
                results.append((sub["key"], sub["fields"]["summary"], "subtask"))

        return results
    else:
        logging.error(f"Failed to fetch tickets: {resp.text}")
        return []



# -----------------------
# Routes
# -----------------------
@app.get("/health")
def healthcheck():
    return {"status": "ok"}


@app.post("/slack/events")
async def slack_events(req: Request):
    body = await req.json()

    # Slack URL verification
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    if event.get("type") == "message" and "bot_id" not in event:
        user_text = event.get("text", "").strip()
        channel = event.get("channel")
        user_id = event.get("user")

        # Map Slack user -> Jira email
        slack_email = get_slack_user_email(user_id)
        if not slack_email:
            slack_client.chat_postMessage(
                channel=channel,
                text="⚠️ Could not fetch your Slack email. Please update your Slack profile."
            )
            return {"ok": True}

        jira_email = slack_email  # ✅ Simple mapping: assume same email in Slack & Jira

        # Case 1: Tickets
        if user_text.lower() == "tickets":
            tickets = fetch_user_tickets(jira_email)
            if tickets:
                ticket_list = "\n".join([f"{i+1}. {t[0]}: {t[1]}" for i, t in enumerate(tickets)])
                slack_client.chat_postMessage(
                    channel=channel,
                    text=f"Here are your tickets:\n{ticket_list}\n\nReply with `ISSUE_KEY your log message`\nOr use `desc ISSUE_KEY your text` to update description."
                )
            else:
                slack_client.chat_postMessage(channel=channel, text="No tickets assigned to you 🚫")

        # Case 2: Update description
        elif user_text.lower().startswith("desc "):
            parts = user_text.split(" ", 2)
            if len(parts) >= 3:
                issue_key, new_text = parts[1], parts[2]
                status, _ = update_issue_description(issue_key, new_text)
                slack_client.chat_postMessage(
                    channel=channel,
                    text=f"📝 Updated description for {issue_key} (status: {status})"
                )

        # Case 3: Log work
        else:
            parts = user_text.split(" ", 1)
            if len(parts) == 2:
                issue_key, log_msg = parts[0], parts[1]
                status, _ = log_to_jira_worklog(issue_key, log_msg, "1h")
                slack_client.chat_postMessage(
                    channel=channel,
                    text=f"✅ Logged to Jira ({issue_key}): {log_msg} (status: {status})"
                )

    return {"ok": True}
