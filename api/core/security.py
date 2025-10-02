from dotenv import load_dotenv
from fastapi import Header, status, HTTPException
import os

load_dotenv()


POSTGRES_USER = os.getenv("DB_USER")
POSTGRES_PASSWORD = os.getenv("DB_PASSWORD")
POSTGRES_DB = os.getenv("DB_NAME")
POSTGRES_PORT = os.getenv("DB_PORT")
SECRET_KEY_OPENAI = os.getenv("SECRET_KEY_OPENAI")
SECRET_ADMIN_TOKEN = os.getenv("SECRET_ADMIN_TOKEN")

def verify_admin_token(x_admin_token: str = Header(..., alias="X-Admin-Token")):
    if x_admin_token != SECRET_ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")
    return True