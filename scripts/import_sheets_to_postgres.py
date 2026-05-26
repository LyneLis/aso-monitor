import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import Settings
from database import PostgresAppsRepository
from sheets import GspreadAppsRepository
from sheets.serialization import tracked_info_from_row


def load_sheet_apps(repo: GspreadAppsRepository):
    data = {}
    for _, row in repo.iter_rows():
        info = tracked_info_from_row(
            row.get("package_id"),
            row.get("geo"),
            row.get("chat_id"),
            title=row.get("title"),
            summary=row.get("summary"),
            description=row.get("description"),
            icon=row.get("icon"),
            header_image=row.get("header_image"),
            screenshots=row.get("screenshots"),
            history=row.get("history"),
            check_log=row.get("check_log"),
            ai_audit=row.get("ai_audit"),
        )
        if not info:
            continue
        key = info.pop("_storage_key")
        data[key] = info
    return data


def main():
    settings = Settings.from_env()
    sheets_repo = GspreadAppsRepository(settings)
    sheets_repo.open()

    users = {}
    # The bot repository reads only the apps worksheet. Streamlit remains the
    # source for user names until the service is fully moved to Postgres.
    apps = load_sheet_apps(sheets_repo)

    postgres_repo = PostgresAppsRepository(settings)
    summary = postgres_repo.import_tracked_apps(apps, users=users)
    counts = postgres_repo.count_rows()

    print("Import complete")
    print(f"Imported locales: {summary['locales']}")
    print(f"Skipped rows: {summary['skipped']}")
    print(f"Tracked apps in Postgres: {counts['tracked_apps']}")
    print(f"Tracked locales in Postgres: {counts['tracked_locales']}")
    print(f"Check logs in Postgres: {counts['check_logs']}")


if __name__ == "__main__":
    main()
