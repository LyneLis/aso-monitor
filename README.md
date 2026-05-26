# ASO Monitor PRO

ASO Monitor PRO watches Google Play and App Store app metadata across locales, stores the current state in Google Sheets, and sends Telegram alerts when titles, descriptions, icons, feature graphics, or screenshots change. It also uses Gemini for ASO analysis of text changes.

## Project Structure

- `app.py` - Streamlit web interface for adding apps, manual checks, audits, and viewing monitored locales.
- `bot.py` - scheduled checker used by GitHub Actions.
- `core/` - comparison logic, parsers, Telegram client, Gemini client, settings, and formatting helpers.
- `sheets/` - Google Sheets repositories and row serialization.
- `tests/` - focused tests for comparison, serialization, Telegram helpers, subtitle decoding, and bot recovery cases.

## Required Secrets

The project uses these values:

- `TELEGRAM_TOKEN` - Telegram bot token.
- `GEMINI_API_KEY` - Gemini API key for AI analysis.
- `SPREADSHEET_URL` - Google Sheet URL. If omitted, the default URL from `core/config.py` is used.
- `GCP_SERVICE_ACCOUNT_JSON` - full Google service account JSON as one environment variable. Required for `bot.py`.

The Google Sheet is expected to have:

- `apps` worksheet for monitored app rows.
- `users` worksheet with at least `name` and `chat_id` columns.

## Local Bot Setup

Create a virtual environment and install the bot dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-bot.txt
```

Create a local `.env` from the example and fill in real values:

```bash
cp .env.example .env
```

Load the variables before running the bot:

```bash
set -a
source .env
set +a
python bot.py
```

## Local Web App Setup

Install the full Streamlit dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml` locally. The `.streamlit/` folder is ignored by git.

```toml
TELEGRAM_TOKEN = "<telegram-bot-token>"
GEMINI_API_KEY = "<gemini-api-key>"
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/.../edit"

[connections.gsheets]
spreadsheet = "https://docs.google.com/spreadsheets/d/.../edit"
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

Run the web app:

```bash
streamlit run app.py
```

## Tests

```bash
python -m pytest -q
```

GitHub Actions installs `requirements-bot.txt` and runs the test suite before `bot.py`.
The bot requirements are pinned for the workflow runtime on Python 3.11.

## GitHub Actions

The scheduled workflow is in `.github/workflows/aso_v2.yml` and runs every 12 hours. Configure these repository secrets:

- `TELEGRAM_TOKEN`
- `GCP_SERVICE_ACCOUNT_JSON`
- `GEMINI_API_KEY`
- `SPREADSHEET_URL`

There is also a monthly keep-alive workflow in `.github/workflows/keep_alive.yml`.

## Operational Notes

- `bot.py` is the source of scheduled automatic checks.
- `app.py` is useful for manual checks, adding locales, deleting entries, and requesting ASO audits.
- A row with a table error such as `#ERROR!` is repaired from fresh store data instead of being reported as a competitor change.
- Telegram request failures are logged instead of being silently ignored.
