"""API zgłoszeń helpdesk: tworzenie zgłoszeń, obieg statusów, komentarze i terminy SLA."""
import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status

from . import db, workflow
from .schemas import Comment, CommentCreate, Priority, Stats, Status, StatusChange, Ticket, TicketCreate


def _ts(value):
    """Zapisuje datę zawsze w tym samym formacie, żeby porównania dat w SQL były poprawne."""
    return value.isoformat(timespec="seconds")


def create_app(db_path=None, clock=workflow.utcnow):
    """Tworzy aplikację. Uruchomienie: uvicorn app.main:create_app --factory

    Parametr clock pozwala testom sterować czasem przy sprawdzaniu SLA.
    """
    db_path = db_path or os.environ.get("HELPDESK_DB", "helpdesk.db")
    db.init_db(db_path)
    app = FastAPI(title="Helpdesk Ticket API", version="1.0.0")

    def get_conn():
        conn = db.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    def require_api_key(x_api_key: str | None = Header(default=None)):
        expected = os.environ.get("HELPDESK_API_KEY")
        if not expected:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Klucz API nie jest skonfigurowany")
        if not x_api_key or not secrets.compare_digest(x_api_key, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy klucz API")

    auth = [Depends(require_api_key)]

    def fetch_ticket(conn, ticket_id):
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Zgłoszenie nie istnieje")
        return dict(row)

    def record_status(conn, ticket_id, from_status, to_status, when):
        conn.execute(
            "INSERT INTO status_history (ticket_id, from_status, to_status, changed_at) VALUES (?, ?, ?, ?)",
            (ticket_id, from_status, to_status, when),
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/tickets", response_model=Ticket, status_code=201, dependencies=auth)
    def create_ticket(payload: TicketCreate, conn=Depends(get_conn)):
        now = clock()
        created = _ts(now)
        due = _ts(workflow.due_date(payload.priority, now))
        cursor = conn.execute(
            "INSERT INTO tickets (title, description, category, priority, status, reporter_email, "
            "created_at, due_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (payload.title, payload.description, payload.category, payload.priority, "nowe",
             payload.reporter_email.lower(), created, due, created),
        )
        record_status(conn, cursor.lastrowid, None, "nowe", created)
        conn.commit()
        return fetch_ticket(conn, cursor.lastrowid)

    @app.get("/tickets", response_model=list[Ticket], dependencies=auth)
    def list_tickets(
        status_filter: Status | None = Query(default=None, alias="status"),
        priority: Priority | None = None,
        conn=Depends(get_conn),
    ):
        conditions, params = [], []
        if status_filter:
            conditions.append("status = ?")
            params.append(status_filter)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        sql = "SELECT * FROM tickets"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        return [dict(row) for row in conn.execute(sql + " ORDER BY id", params)]

    @app.get("/tickets/{ticket_id}", response_model=Ticket, dependencies=auth)
    def get_ticket(ticket_id: int, conn=Depends(get_conn)):
        return fetch_ticket(conn, ticket_id)

    @app.patch("/tickets/{ticket_id}/status", response_model=Ticket, dependencies=auth)
    def change_status(ticket_id: int, payload: StatusChange, conn=Depends(get_conn)):
        current = fetch_ticket(conn, ticket_id)["status"]
        if not workflow.can_transition(current, payload.status):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Niedozwolone przejście: {current} -> {payload.status}")
        if payload.status in workflow.COMMENT_REQUIRED and not payload.comment:
            raise HTTPException(422, f"Status {payload.status} wymaga komentarza")
        now = _ts(clock())
        conn.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (payload.status, now, ticket_id))
        record_status(conn, ticket_id, current, payload.status, now)
        if payload.comment:
            conn.execute(
                "INSERT INTO comments (ticket_id, author, text, created_at) VALUES (?, ?, ?, ?)",
                (ticket_id, "system", payload.comment, now),
            )
        conn.commit()
        return fetch_ticket(conn, ticket_id)

    @app.post("/tickets/{ticket_id}/comments", response_model=Comment, status_code=201, dependencies=auth)
    def add_comment(ticket_id: int, payload: CommentCreate, conn=Depends(get_conn)):
        fetch_ticket(conn, ticket_id)
        cursor = conn.execute(
            "INSERT INTO comments (ticket_id, author, text, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, payload.author, payload.text, _ts(clock())),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM comments WHERE id = ?", (cursor.lastrowid,)).fetchone())

    @app.get("/tickets/{ticket_id}/comments", response_model=list[Comment], dependencies=auth)
    def list_comments(ticket_id: int, conn=Depends(get_conn)):
        fetch_ticket(conn, ticket_id)
        rows = conn.execute("SELECT * FROM comments WHERE ticket_id = ? ORDER BY id", (ticket_id,))
        return [dict(row) for row in rows]

    @app.get("/tickets/{ticket_id}/history", dependencies=auth)
    def history(ticket_id: int, conn=Depends(get_conn)):
        fetch_ticket(conn, ticket_id)
        rows = conn.execute(
            "SELECT from_status, to_status, changed_at FROM status_history WHERE ticket_id = ? ORDER BY id",
            (ticket_id,),
        )
        return [dict(row) for row in rows]

    @app.get("/stats", response_model=Stats, dependencies=auth)
    def stats(conn=Depends(get_conn)):
        counts = {name: 0 for name in workflow.STATUSES}
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM tickets GROUP BY status"):
            counts[row["status"]] = row["n"]
        placeholders = ", ".join("?" * len(workflow.OPEN_STATUSES))
        overdue = conn.execute(
            f"SELECT COUNT(*) FROM tickets WHERE status IN ({placeholders}) AND due_at < ?",
            (*workflow.OPEN_STATUSES, _ts(clock())),
        ).fetchone()[0]
        open_total = sum(counts[name] for name in workflow.OPEN_STATUSES)
        return {"by_status": counts, "open_total": open_total, "overdue": overdue}

    return app
