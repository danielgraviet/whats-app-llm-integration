import os

from dotenv import load_dotenv

env = os.getenv("APP_ENV", "local")
load_dotenv(f".env.{env}")


class Settings:
    FIREBASE_CREDS_PATH = os.getenv("FIREBASE_CREDS_PATH")
    FIREBASE_CREDS_JSON = os.getenv("FIREBASE_CREDS_JSON")
    PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
    WHATSAPP_BUSINESS_ACC_ID = os.getenv("WHATSAPP_BUSINESS_ACC_ID")
    ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    TRUST_CHECK_INTERVAL = int(os.getenv("TRUST_CHECK_INTERVAL", "3"))
    # Debrief the participant and end the study conversation after this many
    # user messages in the normal (LLM) phase. The intro and rating replies
    # do not count.
    DEBRIEF_AFTER_TURNS = int(os.getenv("DEBRIEF_AFTER_TURNS", "8"))
    # Deployed git commit, for the /health endpoint. Railway injects
    # RAILWAY_GIT_COMMIT_SHA automatically; GIT_COMMIT_SHA is a manual override.
    GIT_COMMIT_SHA = os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA")
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
    USE_FLOWS = os.getenv("USE_FLOWS", "false").lower() == "true"
    FLOW_ID_EN = os.getenv("FLOW_ID_EN", "123")
    FLOW_ID_PT = os.getenv("FLOW_ID_PT", "123")


settings = Settings()
