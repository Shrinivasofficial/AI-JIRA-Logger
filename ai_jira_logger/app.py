from fastapi import FastAPI
from ai_jira_logger.config import validate_config
from ai_jira_logger.slack_routes import router as slack_router

# Validate env/config before starting
validate_config()

app = FastAPI(title="AI JIRA Logger")

# Health check route
@app.get("/health")
def healthcheck():
    return {"status": "ok"}

# Root route so visiting "/" works in browser
@app.get("/")
def root():
    return {"message": "AI JIRA Logger service is running."}

# Include Slack event routes
app.include_router(slack_router)
