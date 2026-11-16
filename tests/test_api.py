from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

KEY = "test-key"
HEADERS = {"X-API-Key": KEY}
BASE = {
    "title": "Nie działa drukarka",
    "description": "Drukarka na drugim piętrze nie drukuje od rana.",
    "category": "sprzet",
    "priority": "wysoki",
    "reporter_email": "Jan.Kowalski@example.edu.pl",
}


class FakeClock:
    """Zegar sterowany z testu, żeby sprawdzać terminy SLA bez czekania."""

    def __init__(self):
        self.now = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def client(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("HELPDESK_API_KEY", KEY)
    app = create_app(str(tmp_path / "test.db"), clock=clock)
    with TestClient(app) as test_client:
        yield test_client


def new_ticket(client, **overrides):
    payload = dict(BASE, **overrides)
    response = client.post("/tickets", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client, ticket_id, target, comment=None):
    body = {"status": target}
    if comment:
        body["comment"] = comment
    return client.patch(f"/tickets/{ticket_id}/status", json=body, headers=HEADERS)


def test_health_bez_klucza(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_brak_klucza_api(client):
    assert client.get("/tickets").status_code == 401


def test_bledny_klucz_api(client):
    assert client.get("/tickets", headers={"X-API-Key": "zly"}).status_code == 401


def test_klucz_nieskonfigurowany(client, monkeypatch):
    monkeypatch.delenv("HELPDESK_API_KEY")
    assert client.get("/tickets", headers=HEADERS).status_code == 503


def test_utworzenie_zgloszenia(client):
    ticket = new_ticket(client)
    assert ticket["status"] == "nowe"
    assert ticket["reporter_email"] == "jan.kowalski@example.edu.pl"
    created = datetime.fromisoformat(ticket["created_at"])
    due = datetime.fromisoformat(ticket["due_at"])
    assert due - created == timedelta(hours=8)


@pytest.mark.parametrize(
    "field, value",
    [
        ("title", "abc"),
        ("reporter_email", "brak-malpy"),
        ("category", "kawa"),
        ("priority", "pilne"),
    ],
)
def test_walidacja_danych(client, field, value):
    payload = dict(BASE, **{field: value})
    assert client.post("/tickets", json=payload, headers=HEADERS).status_code == 422


def test_nieistniejace_zgloszenie(client):
    assert client.get("/tickets/999", headers=HEADERS).status_code == 404


def test_pelny_obieg(client):
    ticket_id = new_ticket(client)["id"]
    for target in ("w_trakcie", "rozwiazane", "zamkniete"):
        response = set_status(client, ticket_id, target)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target
    history = client.get(f"/tickets/{ticket_id}/history", headers=HEADERS).json()
    assert [entry["to_status"] for entry in history] == ["nowe", "w_trakcie", "rozwiazane", "zamkniete"]


def test_niedozwolone_przejscie(client):
    ticket_id = new_ticket(client)["id"]
    assert set_status(client, ticket_id, "rozwiazane").status_code == 409


def test_zamkniete_nie_zmienia_statusu(client):
    ticket_id = new_ticket(client)["id"]
    assert set_status(client, ticket_id, "zamkniete").status_code == 200
    assert set_status(client, ticket_id, "w_trakcie").status_code == 409


def test_oczekuje_wymaga_komentarza(client):
    ticket_id = new_ticket(client)["id"]
    set_status(client, ticket_id, "w_trakcie")
    assert set_status(client, ticket_id, "oczekuje").status_code == 422
    response = set_status(client, ticket_id, "oczekuje", comment="Czekam na dostawę tonera")
    assert response.status_code == 200
    comments = client.get(f"/tickets/{ticket_id}/comments", headers=HEADERS).json()
    assert comments[-1]["text"] == "Czekam na dostawę tonera"


def test_dodanie_komentarza(client):
    ticket_id = new_ticket(client)["id"]
    body = {"author": "Anna Nowak", "text": "Sprawdzam kabel sieciowy"}
    response = client.post(f"/tickets/{ticket_id}/comments", json=body, headers=HEADERS)
    assert response.status_code == 201
    assert response.json()["ticket_id"] == ticket_id


def test_filtrowanie(client):
    first = new_ticket(client, priority="krytyczny")["id"]
    new_ticket(client, priority="niski")
    set_status(client, first, "w_trakcie")
    by_status = client.get("/tickets?status=w_trakcie", headers=HEADERS).json()
    by_priority = client.get("/tickets?priority=niski", headers=HEADERS).json()
    assert [ticket["id"] for ticket in by_status] == [first]
    assert [ticket["priority"] for ticket in by_priority] == ["niski"]


def test_sla_i_statystyki(client, clock):
    critical = new_ticket(client, priority="krytyczny")["id"]
    new_ticket(client, priority="niski")
    clock.advance(hours=5)
    stats = client.get("/stats", headers=HEADERS).json()
    assert stats["open_total"] == 2
    assert stats["overdue"] == 1
    set_status(client, critical, "w_trakcie")
    set_status(client, critical, "rozwiazane")
    stats = client.get("/stats", headers=HEADERS).json()
    assert stats["overdue"] == 0
    assert stats["by_status"]["rozwiazane"] == 1


def test_wartosci_trafiaja_jako_parametry(client):
    title = "x; DROP TABLE tickets; --"
    ticket_id = new_ticket(client, title=title)["id"]
    assert client.get(f"/tickets/{ticket_id}", headers=HEADERS).json()["title"] == title
    assert len(client.get("/tickets", headers=HEADERS).json()) == 1
