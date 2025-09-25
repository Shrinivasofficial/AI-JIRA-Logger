from fastapi import FastAPI
from ai_jira_logger.config import validate_config
from ai_jira_logger.slack_routes import router as slack_router


validate_config()
app = FastAPI()

@app.get("/health")
def healthcheck():
    return {"status": "ok"}

app.include_router(slack_router)

 