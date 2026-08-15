from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    tenant_slug: str = Field(description="The tenant's subdomain, e.g. 'acme-corp'")
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)
