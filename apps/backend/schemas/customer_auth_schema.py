from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExchangeRequest(BaseModel):
    """Only the identity token. Any other field (notably a customer id) is refused, never ignored silently."""
    model_config = ConfigDict(extra="forbid")

    id_token: str = Field(min_length=1, max_length=4096)


class SessionOut(BaseModel):
    session_token: str
    expires_at: datetime
