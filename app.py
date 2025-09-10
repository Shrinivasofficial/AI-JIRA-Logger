import os
import requests
from fastapi import FastAPI, Request
from slack_sdk import WebClient
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from datetime import datetime

# Load env vars
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")  # e.g., https://your-domain.atlassian.net

slack_client = WebClient(token=SLACK_BOT_TOKEN)

app = FastAPI()

# --- Jira logger ---
def log_to_jira_worklog(issue_key, message, time_spent="30m"):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/worklog"

    payload = {
        "comment": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"text": message, "type": "text"}]
                }
            ]
        },
        "timeSpent": time_spent,
        "started": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    }

    response = requests.post(
        url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Content-Type": "application/json"},
        json=payload
    )
    return response.status_code, response.text


def fetch_user_tickets(jira_email):
    url = f"{JIRA_DOMAIN}/rest/api/3/search"
    jql = f'assignee = "{jira_email}" AND resolution = Unresolved ORDER BY updated DESC'

    response = requests.get(
        url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Content-Type": "application/json"},
        params={"jql": jql, "maxResults": 5}
    )
    if response.status_code == 200:
        data = response.json()
        issues = data.get("issues", [])
        return [(issue["key"], issue["fields"]["summary"]) for issue in issues]
    else:
        return []


def update_issue_description(issue_key, new_text):
    # Step 1: Get current description
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}?fields=description"
    response = requests.get(
        url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json"}
    )

    if response.status_code != 200:
        return response.status_code, f"Failed to fetch description: {response.text}"

    data = response.json()
    current_desc = ""
    try:
        content = data["fields"]["description"]["content"]
        current_desc = "\n".join(
            "".join(part.get("text", "") for part in block.get("content", []))
            for block in content
        )
    except Exception:
        current_desc = ""

    # Step 2: Append new text
    updated_desc = (current_desc + "\n" + new_text).strip()

    # Step 3: Push update
    update_url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}"
    payload = {
        "fields": {
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"text": updated_desc, "type": "text"}]
                    }
                ]
            }
        }
    }

    put_resp = requests.put(
        update_url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Content-Type": "application/json"},
        json=payload
    )
    return put_resp.status_code, put_resp.text


# --- Slack events ---
@app.post("/slack/events")
async def slack_events(req: Request):
    body = await req.json()

    # Slack verification challenge
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    if event.get("type") == "message" and "bot_id" not in event:
        user_text = event.get("text", "").strip()
        channel = event.get("channel")

        # Case 1: User asks for tickets
        if user_text.lower() == "tickets":
            tickets = fetch_user_tickets(JIRA_EMAIL)  # TODO: map Slack user -> Jira email
            if tickets:
                ticket_list = "\n".join([f"{i+1}. {t[0]}: {t[1]}" for i, t in enumerate(tickets)])
                slack_client.chat_postMessage(
                    channel=channel,
                    text=f"Here are your tickets:\n{ticket_list}\n\nReply with ISSUE_KEY + message to log work.\nOr use `desc ISSUE_KEY your text` to update description."
                )
            else:
                slack_client.chat_postMessage(channel=channel, text="No tickets assigned to you 🚫")

        # Case 2: User updates description
        elif user_text.lower().startswith("desc "):
            parts = user_text.split(" ", 2)
            if len(parts) >= 3:
                issue_key, new_text = parts[1], parts[2]
                status, resp = update_issue_description(issue_key, new_text)
                slack_client.chat_postMessage(
                    channel=channel,
                    text=f"📝 Updated description for {issue_key} (status: {status})"
                )

        # Case 3: User logs work (first word = issue key)
        else:
            parts = user_text.split(" ", 1)
            if len(parts) == 2:
                issue_key, log_msg = parts[0], parts[1]
                status, res_text = log_to_jira_worklog(issue_key, log_msg, "1h")
                slack_client.chat_postMessage(
                    channel=channel,
                    text=f"✅ Logged to Jira ({issue_key}): {log_msg} (status: {status})"
                )

    return {"ok": True}
