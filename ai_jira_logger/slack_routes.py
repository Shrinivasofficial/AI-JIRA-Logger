from fastapi import APIRouter, Request
from ai_jira_logger.slack_helpers import slack_client, get_slack_user_email
from ai_jira_logger.jira_helpers import (
    fetch_user_tickets,
    update_issue_description,
    log_to_jira_worklog,
    add_comment,
    fetch_subtasks,
    fetch_issue_details,
)
from ai_jira_logger.ai_helpers import enhance_description

router = APIRouter()

@router.post("/slack/events")
async def slack_events(req: Request):
    body = await req.json()

    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    if event.get("type") == "message" and "bot_id" not in event:
        user_text = event.get("text", "").strip()
        channel, user_id = event.get("channel"), event.get("user")

        slack_email = get_slack_user_email(user_id)
        if not slack_email:
            slack_client.chat_postMessage(channel=channel, text="⚠️ Could not fetch your Slack email.")
            return {"ok": True}

        jira_email = slack_email

        # ---- Commands ----
        if user_text.lower() == "tickets":
            tickets = fetch_user_tickets(jira_email)
            if tickets:
                ticket_list = "\n".join([f"{i+1}. {t[0]}: {t[1]}" for i, t in enumerate(tickets)])
                slack_client.chat_postMessage(channel=channel, text=f"Here are your tickets:\n{ticket_list}")
            else:
                slack_client.chat_postMessage(channel=channel, text="🚫 No tickets assigned to you.")

        elif user_text.lower().startswith("desc "):
            _, issue_key, new_text = user_text.split(" ", 2)
            status, _ = update_issue_description(issue_key, new_text)
            slack_client.chat_postMessage(channel=channel, text=f"📝 Updated {issue_key} (status: {status})")

        elif user_text.lower().startswith("descai "):
            _, issue_key, raw_text = user_text.split(" ", 2)
            enhanced = enhance_description(raw_text)
            status, _ = update_issue_description(issue_key, enhanced)
            slack_client.chat_postMessage(channel=channel, text=f"🤖 AI-enhanced {issue_key} (status: {status})\n{enhanced}")

        elif user_text.lower().startswith("comment "):
            _, issue_key, comment_text = user_text.split(" ", 2)
            status, _ = add_comment(issue_key, comment_text)
            slack_client.chat_postMessage(channel=channel, text=f"💬 Comment added to {issue_key} (status: {status})")

        elif user_text.lower().startswith("subtasks "):
            _, issue_key = user_text.split(" ", 1)
            subtasks = fetch_subtasks(issue_key)
            if subtasks:
                msg = "\n".join([f"- {s[0]}: {s[1]} ({s[2]})" for s in subtasks])
                slack_client.chat_postMessage(channel=channel, text=f"🧩 Subtasks:\n{msg}")
            else:
                slack_client.chat_postMessage(channel=channel, text=f"No subtasks for {issue_key}")

        elif user_text.lower().startswith("details "):
            _, issue_key = user_text.split(" ", 1)
            details = fetch_issue_details(issue_key)
            if details:
                desc_preview = " ".join(
                    "".join(p.get("text", "") for p in block.get("content", []))
                    for block in details["description"]
                )[:200] + "..."
                msg = (f"📌 *{issue_key}*: {details['summary']}\n"
                       f"📝 Status: {details['status']}\n"
                       f"🙋 Assignee: {details['assignee']}\n"
                       f"👤 Reporter: {details['reporter']}\n"
                       f"📅 Due date: {details['due_date']}\n"
                       f"🧾 Description: {desc_preview}")
                slack_client.chat_postMessage(channel=channel, text=msg)
            else:
                slack_client.chat_postMessage(channel=channel, text=f"⚠️ Could not fetch details for {issue_key}")

        else:
            parts = user_text.split(" ", 1)
            if len(parts) == 2:
                issue_key, log_msg = parts
                status, _ = log_to_jira_worklog(issue_key, log_msg, "1h")
                slack_client.chat_postMessage(channel=channel, text=f"✅ Logged work to {issue_key} (status: {status})")

    return {"ok": True}
