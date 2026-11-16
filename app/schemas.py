"""Schematy danych wejściowych i wyjściowych API (walidacja Pydantic)."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["sprzet", "oprogramowanie", "dostep", "siec", "inne"]
Priority = Literal["krytyczny", "wysoki", "sredni", "niski"]
Status = Literal["nowe", "w_trakcie", "oczekuje", "rozwiazane", "zamkniete"]

EMAIL_PATTERN = r"^[^@ ]+@[^@ ]+[.][A-Za-z]{2,}$"


class TicketCreate(BaseModel):
    title: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=10, max_length=4000)
    category: Category
    priority: Priority = "sredni"
    reporter_email: str = Field(pattern=EMAIL_PATTERN, max_length=254)


class Ticket(BaseModel):
    id: int
    title: str
    description: str
    category: Category
    priority: Priority
    status: Status
    reporter_email: str
    created_at: datetime
    due_at: datetime
    updated_at: datetime


class StatusChange(BaseModel):
    status: Status
    comment: Optional[str] = Field(default=None, max_length=2000)


class CommentCreate(BaseModel):
    author: str = Field(min_length=2, max_length=80)
    text: str = Field(min_length=1, max_length=2000)


class Comment(BaseModel):
    id: int
    ticket_id: int
    author: str
    text: str
    created_at: datetime


class Stats(BaseModel):
    by_status: dict[str, int]
    open_total: int
    overdue: int
