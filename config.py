import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    FIREBASE_CREDS_PATH = os.getenv("FIREBASE_CREDS_PATH")
    FIREBASE_CREDS_JSON = os.getenv("FIREBASE_CREDS_JSON")
    PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
    WHATSAPP_BUSINESS_ACC_ID = os.getenv("WHATSAPP_BUSINESS_ACC_ID")
    ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    TRUST_CHECK_INTERVAL = int(os.getenv("TRUST_CHECK_INTERVAL", "3"))


settings = Settings()
