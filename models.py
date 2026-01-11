from pydantic import BaseModel, EmailStr
from typing import List, Optional

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    interests: Optional[List[str]] = []

class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    interests: Optional[List[str]] = []
    created_at: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class CVUploadOut(BaseModel):
    id: int
    file_path: str
    uploaded_at: str
