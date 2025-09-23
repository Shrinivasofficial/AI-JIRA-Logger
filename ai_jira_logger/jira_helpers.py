import requests, logging
from requests.auth import HTTPBasicAuth
from datetime import datetime
import re
from ai_jira_logger.config import JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, validate_config

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
headers = {"Content-Type": "application/json", "Accept": "application/json"}

def normalize_time_spent(time_str: str) -> str:
    return time_str.replace(" ", "").lower()


def parse_slack_worklog(slack_message: str):
    """
    Parses Slack message like:
    ISSUE_KEY WORK_LOG_TEXT - TIME_SPENT
    Example: "SCRUM-1 TESTING WORK LOGGING - 2h"
    """
    parts = slack_message.strip().split(" ", 1)
    if len(parts) < 2:
        raise ValueError("Invalid format. Must include ISSUE_KEY and message")

    issue_key = parts[0]
    rest = parts[1]

    if "-" not in rest:
        raise ValueError("Invalid format. Must include '-' before time spent")

    message_part, time_part = rest.rsplit("-", 1)
    message = message_part.strip()
    time_spent = normalize_time_spent(time_part.strip())
    return issue_key, message, time_spent


def log_to_jira_worklog(issue_key: str, message: str, time_spent: str):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/worklog"
    payload = {
        "comment": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"text": message, "type": "text"}]}]
        },
        "timeSpent": time_spent,
        "started": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
    }
    resp = requests.post(url, auth=auth, headers=headers, json=payload)
    return resp.status_code, resp.text



def fetch_user_tickets(jira_email: str):
    url = f"{JIRA_DOMAIN}/rest/api/3/search"
    jql = f'assignee = "{jira_email}" AND resolution = Unresolved ORDER BY updated DESC'
    resp = requests.get(url, auth=auth, headers=headers, params={"jql": jql, "maxResults": 5})
    if resp.status_code == 200:
        return [(i["key"], i["fields"]["summary"]) for i in resp.json().get("issues", [])]
    return []

def update_issue_description(issue_key: str, new_text: str):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}"
    payload = {
        "fields": {
            "description": {"type": "doc", "version": 1,
                            "content": [{"type": "paragraph", "content": [{"text": new_text, "type": "text"}]}]}
        }
    }
    resp = requests.put(url, auth=auth, headers=headers, json=payload)
    return resp.status_code, resp.text

def add_comment(issue_key: str, comment: str):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/comment"
    payload = {
        "body": {"type": "doc", "version": 1,
                 "content": [{"type": "paragraph", "content": [{"text": comment, "type": "text"}]}]}
    }
    resp = requests.post(url, auth=auth, headers=headers, json=payload)
    return resp.status_code, resp.text

def fetch_subtasks(issue_key: str):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}?fields=subtasks"
    resp = requests.get(url, auth=auth, headers=headers)
    if resp.status_code == 200:
        return [(s["key"], s["fields"]["summary"], s["fields"]["status"]["name"]) for s in resp.json()["fields"].get("subtasks", [])]
    return []

def fetch_issue_details(issue_key: str):
    """
    Fetch detailed information for a Jira issue safely,
    handling missing assignee, reporter, or description.
    """
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}"
    resp = requests.get(url, auth=auth, headers=headers)

    if resp.status_code != 200:
        return None

    data = resp.json()
    fields = data.get("fields", {})

    # Safely extract assignee
    assignee_info = fields.get("assignee")
    assignee_name = assignee_info.get("displayName") if assignee_info else "Unassigned"

    # Safely extract reporter
    reporter_info = fields.get("reporter")
    reporter_name = reporter_info.get("displayName") if reporter_info else "Unknown"

    # Safely extract description content
    description_info = fields.get("description")
    description_content = description_info.get("content", []) if description_info else []

    return {
        "summary": fields.get("summary", ""),
        "status": fields.get("status", {}).get("name", ""),
        "assignee": assignee_name,
        "reporter": reporter_name,
        "due_date": fields.get("duedate", "None"),
        "description": description_content,
    }

def transition_issue(issue_key: str, transition_id: str):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/transitions"
    payload = {"transition": {"id": transition_id}}
    resp = requests.post(url, auth=auth, headers=headers, json=payload)
    return resp.status_code, resp.text

def get_transitions(issue_key: str):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/transitions"
    resp = requests.get(url, auth=auth, headers=headers)
    return resp.json() if resp.status_code == 200 else []

def create_subtask(parent_key: str, summary: str, description: str, project_key: str):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue"
    payload = {
        "fields": {
            "project": {"key": project_key},
            "parent": {"key": parent_key},
            "summary": summary,
            "description": {"type": "doc", "version": 1,
                            "content": [{"type": "paragraph", "content": [{"text": description, "type": "text"}]}]},
            "issuetype": {"name": "Sub-task"},
        }
    }
    resp = requests.post(url, auth=auth, headers=headers, json=payload)
    return resp.status_code, resp.json() if resp.status_code == 201 else resp.text

def create_issue(project_key: str, summary: str, description: str, issue_type: str = "Task"):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue"
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {"type": "doc", "version": 1,
                            "content": [{"type": "paragraph", "content": [{"text": description, "type": "text"}]}]},
            "issuetype": {"name": issue_type},
        }
    }
    resp = requests.post(url, auth=auth, headers=headers, json=payload)
    return resp.status_code, resp.json() if resp.status_code == 201 else resp.text