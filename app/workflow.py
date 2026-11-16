"""Reguły obiegu zgłoszenia: dozwolone przejścia statusów i terminy SLA."""
from datetime import datetime, timedelta, timezone

STATUSES = ("nowe", "w_trakcie", "oczekuje", "rozwiazane", "zamkniete")
OPEN_STATUSES = ("nowe", "w_trakcie", "oczekuje")

TRANSITIONS = {
    "nowe": {"w_trakcie", "zamkniete"},
    "w_trakcie": {"oczekuje", "rozwiazane"},
    "oczekuje": {"w_trakcie"},
    "rozwiazane": {"zamkniete", "w_trakcie"},
    "zamkniete": set(),
}

# Statusy, przy których trzeba podać komentarz (np. na co czeka zgłoszenie).
COMMENT_REQUIRED = {"oczekuje"}

# Czas na rozwiązanie zgłoszenia w godzinach, zależnie od priorytetu.
SLA_HOURS = {"krytyczny": 4, "wysoki": 8, "sredni": 24, "niski": 72}


def can_transition(current, target):
    """Zwraca True, gdy przejście ze statusu current do target jest dozwolone."""
    return target in TRANSITIONS.get(current, set())


def due_date(priority, created_at):
    """Termin SLA: data utworzenia plus czas przypisany do priorytetu."""
    return created_at + timedelta(hours=SLA_HOURS[priority])


def utcnow():
    return datetime.now(timezone.utc)
