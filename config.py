import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev")
    SESSION_TYPE = "filesystem"
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    DEBUG = False
    DATABASE_URL = os.getenv("DATABASE_URL")
    DATABASE_URL_LOG = os.getenv("DATABASE_URL_LOG")
    DATABASE_URL_RGPD = os.getenv("DATABASE_URL_RGPD")

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False  # 🔒 Important
    if os.getenv("FLASK_SECRET_KEY") is None:
        raise RuntimeError("❌ FLASK_SECRET_KEY obligatoire en production.")