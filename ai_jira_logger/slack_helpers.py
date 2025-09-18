import logging
from slack_sdk import WebClient
from ai_jira_logger.config import SLACK_BOT_TOKEN  

slack_client = WebClient(token=SLACK_BOT_TOKEN)

def get_slack_user_email(user_id: str):
    try:
        resp = slack_client.users_info(user=user_id)
        if resp["ok"]:
            return resp["user"]["profile"].get("email")
    except Exception as e:
        logging.error(f"Slack API error: {e}")
    return None
