from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(faculty|student|employer|advisor)$")
    join_code: str | None = None       # join an existing organization
    org_name: str | None = None        # or create a new one (you become its admin)
    company: str | None = None


def user_out(u) -> dict:
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role, "company": u.company,
            "org": {"id": u.org.id, "name": u.org.name, "slug": u.org.slug, "plan": u.org.plan}}
