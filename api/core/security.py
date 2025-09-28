from dotenv import load_dotenv
import os

load_dotenv()


POSTGRES_USER = os.getenv("DB_USER")
POSTGRES_PASSWORD = os.getenv("DB_PASSWORD")
POSTGRES_DB = os.getenv("DB_NAME")
POSTGRES_PORT = os.getenv("DB_PORT")
SECRET_KEY_OPENAI = os.getenv("SECRET_KEY_OPENAI")