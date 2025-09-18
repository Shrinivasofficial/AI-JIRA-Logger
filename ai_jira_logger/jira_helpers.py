import requests, logging
from requests.auth import HTTPBasicAuth
from datetime import datetime
from ai_jira_logger.config import JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, validate_config

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
headers = {"Content-Type": "application/json", "Accept": "application/json"}

def log_to_jira_worklog(issue_key: str, message: str, time_spent: str = "30m"):
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/worklog"
    payload = {
        "comment": {"type": "doc", "version": 1,
                    "content": [{"type": "paragraph", "content": [{"text": message, "type": "text"}]}]},
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
    url = f"{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}"
    resp = requests.get(url, auth=auth, headers=headers)
    if resp.status_code == 200:
        f = resp.json()["fields"]
        return {
            "summary": f.get("summary", ""),
            "status": f.get("status", {}).get("name", ""),
            "assignee": f.get("assignee", {}).get("displayName", "Unassigned"),
            "reporter": f.get("reporter", {}).get("displayName", "Unknown"),
            "due_date": f.get("duedate", "None"),
            "description": f.get("description", {}).get("content", []),
        }
    return None
