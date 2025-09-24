from fastapi import APIRouter, Request
from ai_jira_logger.slack_helpers import slack_client, get_slack_user_email
from ai_jira_logger.jira_helpers import (
    fetch_user_tickets,
    update_issue_description,
    add_comment,
    fetch_subtasks,
    fetch_issue_details,
)
from ai_jira_logger.confluence_helpers import confluence_answer, refresh_cache
from ai_jira_logger.ai_helpers import enhance_description
import asyncio

router = APIRouter()

# ✅ Warm up Confluence cache at startup
refresh_cache()

# Track processed Slack event IDs to avoid duplication
PROCESSED_EVENTS = set()


@router.post("/slack/events")
async def slack_events(req: Request):
    body = await req.json()

    # Slack URL verification
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    event_id = body.get("event_id") or event.get("client_msg_id")
    if not event_id or event_id in PROCESSED_EVENTS:
        return {"ok": True}  # Skip duplicate event
    PROCESSED_EVENTS.add(event_id)

    if event.get("type") == "message" and "bot_id" not in event:
        user_text = event.get("text", "").strip()
        channel, user_id = event.get("channel"), event.get("user")

        # Jira-related commands
        if user_text.lower().startswith(("tickets", "desc ", "descai ", "comment ", "subtasks ", "details ")):
            slack_email = get_slack_user_email(user_id)
            if not slack_email:
                slack_client.chat_postMessage(channel=channel, text="⚠️ Could not fetch your Slack email.")
                return {"ok": True}
            jira_email = slack_email

            if user_text.lower() == "tickets":
                tickets = fetch_user_tickets(jira_email)
                msg = "\n".join([f"{i+1}. {t[0]}: {t[1]}" for i, t in enumerate(tickets)]) if tickets else "No tickets assigned to you."
                slack_client.chat_postMessage(channel=channel, text=msg)

            elif user_text.lower().startswith("desc "):
                try:
                    _, issue_key, new_text = user_text.split(" ", 2)
                    status, _ = update_issue_description(issue_key, new_text)
                    slack_client.chat_postMessage(channel=channel, text=f"Updated {issue_key} (status: {status})")
                except Exception as e:
                    slack_client.chat_postMessage(channel=channel, text=f"Error updating description: {e}")

            elif user_text.lower().startswith("descai "):
                try:
                    _, issue_key, raw_text = user_text.split(" ", 2)
                    enhanced = enhance_description(raw_text)
                    status, _ = update_issue_description(issue_key, enhanced)
                    slack_client.chat_postMessage(channel=channel, text=f"AI-enhanced {issue_key} (status: {status})\n{enhanced}")
                except Exception as e:
                    slack_client.chat_postMessage(channel=channel, text=f"Error enhancing description: {e}")

            elif user_text.lower().startswith("comment "):
                try:
                    _, issue_key, comment_text = user_text.split(" ", 2)
                    status, _ = add_comment(issue_key, comment_text)
                    slack_client.chat_postMessage(channel=channel, text=f"Comment added to {issue_key} (status: {status})")
                except Exception as e:
                    slack_client.chat_postMessage(channel=channel, text=f"Error adding comment: {e}")

            elif user_text.lower().startswith("subtasks "):
                _, issue_key = user_text.split(" ", 1)
                subtasks = fetch_subtasks(issue_key)
                msg = "\n".join([f"- {s[0]}: {s[1]} ({s[2]})" for s in subtasks]) if subtasks else f"No subtasks for {issue_key}"
                slack_client.chat_postMessage(channel=channel, text=msg)

            elif user_text.lower().startswith("details "):
                _, issue_key = user_text.split(" ", 1)
                details = fetch_issue_details(issue_key)
                if details:
                    desc_preview = " ".join(
                        "".join(p.get("text", "") for p in block.get("content", []))
                        for block in details["description"]
                    )[:200] + "..."
                    msg = (f"{issue_key}: {details['summary']}\n"
                           f"Status: {details['status']}\n"
                           f"Assignee: {details['assignee']}\n"
                           f"Reporter: {details['reporter']}\n"
                           f"Due date: {details['due_date']}\n"
                           f"Description: {desc_preview}")
                    slack_client.chat_postMessage(channel=channel, text=msg)
                else:
                    slack_client.chat_postMessage(channel=channel, text=f"Could not fetch details for {issue_key}")

        else:
            # Non-Jira → Confluence Q&A with typing indicator
            try:
                # Send "typing..." indicator
                slack_client.chat_postMessage(channel=channel, text="_Bot is typing..._")
                
                # Async sleep to simulate typing
                await asyncio.sleep(1)
                
                answer = confluence_answer(user_text)
                slack_client.chat_postMessage(channel=channel, text=answer)
            except Exception as e:
                slack_client.chat_postMessage(channel=channel, text=f"Could not fetch Confluence answer: {e}")

    return {"ok": True}
