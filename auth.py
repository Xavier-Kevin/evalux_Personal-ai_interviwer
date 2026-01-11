# auth.py
# Authentication helpers: loads .env at import time to ensure SECRET_KEY etc are available.

from dotenv import load_dotenv
load_dotenv()  # <<< ensure .env is loaded immediately

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from passlib.context import CryptContext
from passlib.hash import pbkdf2_sha256
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

# password hashing
# Prefer bcrypt_sha256 for new hashes, but allow pbkdf2_sha256 as a reliable fallback
# and keep bcrypt in the list so existing legacy hashes still verify.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "pbkdf2_sha256"],
    deprecated="auto",
)

# env-backed config (safe defaults)
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-default-change-me")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
try:
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
except ValueError:
    ACCESS_TOKEN_EXPIRE_MINUTES = 60

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        # Catch ValueError, UnknownHashError, etc. and treat as failed verification.
        logger.warning("Password verification failed: %s", e)
        return False

def get_password_hash(password: str) -> str:
    return pbkdf2_sha256.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT token. `data` should be a dict with claims (e.g., {"sub": email}).
    """
    to_encode = data.copy()
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

def decode_access_token(token: str) -> dict:
    """
    Decode and validate a token. Raises jose.JWTError on invalid/expired token.
    Returns the claims dict on success.
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    
    try:
        payload = decode_access_token(token)
        user_id = payload.get("user_id")
        email = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return {"user_id": user_id, "email": email}
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )