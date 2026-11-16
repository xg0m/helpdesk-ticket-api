# Reguły pracy z narzędziami AI w tym repozytorium

Plik dla narzędzi AI w wierszu poleceń (Claude Code, Gemini CLI, Codex CLI) i dla osób współpracujących.

## Kontekst

REST API zgłoszeń helpdesk w Pythonie 3.12 (FastAPI, SQLite). Reguły obiegu statusów i SLA są w app/workflow.py, endpointy w app/main.py.

## Reguły

- Wartości do SQL przekazuj wyłącznie jako parametry zapytania.
- Nie zapisuj kluczy ani haseł w kodzie. Klucz API pochodzi ze zmiennej HELPDESK_API_KEY.
- Każda zmiana reguł obiegu lub SLA wymaga testu w tests/test_api.py i aktualizacji tabeli w README.
- Nowy endpoint domyślnie wymaga klucza API.
- Komunikaty błędów dla użytkownika pisz po polsku.

## Sposób pracy

1. Przeczytaj README i app/workflow.py.
2. Najpierw napisz test, potem kod.
3. Uruchom pytest -v.
4. Sprawdź zmiany ręcznie przed zatwierdzeniem. Odpowiedzi AI traktuj jako szkic.
