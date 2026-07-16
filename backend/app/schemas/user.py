from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime

# 用户注册
class UserCreate(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    password: str

# 用户登录
class UserLogin(BaseModel):
    username: str
    password: str

# 修改密码
class PasswordChange(BaseModel):
    old_password: str
    new_password: str

# Token 响应
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# 用户响应
class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True
