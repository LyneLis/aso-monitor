import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from core.config import Settings
from sheets.serialization import storage_key, tracked_info_from_row


ConnectionFactory = Callable[[str], Any]
MINSK_TZ_NAME = "Europe/Minsk"


def _json_cell(value: Any) -> str:
    if value is None:
        return "[]"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _open_psycopg_connection(database_url: str) -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(database_url, row_factory=dict_row)


def _platform_for_package(package_id: str) -> str:
    return "ios" if str(package_id).isdigit() else "android"


def _parse_minsk_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        from zoneinfo import ZoneInfo

        parsed = datetime.strptime(str(value).strip(), "%d.%m.%Y %H:%M:%S")
        return parsed.replace(tzinfo=ZoneInfo(MINSK_TZ_NAME))
    except Exception:
        return None


def _created_at_from_log(log_entry: Dict[str, Any]) -> datetime:
    return _parse_minsk_timestamp(log_entry.get("time")) or datetime.now(timezone.utc)


def _normalize_chat_id(chat_id: Any) -> str:
    value = str(chat_id or "").strip()
    if not value or value.lower() == "nan":
        return "unassigned"
    return value


def _user_name_for_chat_id(chat_id: str, known_users: Dict[str, Any]) -> str:
    for name, known_chat_id in known_users.items():
        if str(known_chat_id) == str(chat_id):
            return str(name)
    return f"User {chat_id}"


class PostgresAppsRepository:
    def __init__(
        self,
        settings: Settings,
        *,
        connection_factory: Optional[ConnectionFactory] = None,
    ):
        self._database_url = settings.database_url
        self._connection_factory = connection_factory or _open_psycopg_connection

    @property
    def available(self) -> bool:
        return bool(self._database_url)

    def _connect(self) -> Any:
        if not self._database_url:
            raise ValueError("DATABASE_URL не задан")
        return self._connection_factory(self._database_url)

    def ping(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("select 1 as ok").fetchone()
        if isinstance(row, dict):
            return row.get("ok") == 1
        return bool(row)

    def load_users(self) -> Dict[str, Any]:
        query = """
            select name, chat_id
            from public.monitor_users
            order by name
        """
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return {row["name"]: row["chat_id"] for row in rows}

    def load_apps(self) -> Dict[str, Dict[str, Any]]:
        query = """
            select
                app.package_id,
                locale.geo,
                app.owner_chat_id as chat_id,
                locale.title,
                locale.summary,
                locale.description,
                locale.icon,
                locale.header_image,
                locale.screenshots,
                coalesce(logs.check_log, '[]'::jsonb) as check_log,
                coalesce(audit.audit_text, '') as ai_audit
            from public.tracked_locales locale
            join public.tracked_apps app on app.id = locale.app_id
            left join lateral (
                select jsonb_agg(
                    jsonb_strip_nulls(
                        jsonb_build_object(
                            'time', to_char(recent.created_at at time zone 'Europe/Minsk', 'DD.MM.YYYY HH24:MI:SS'),
                            'status', recent.status,
                            'error', recent.error
                        )
                    )
                    order by recent.created_at
                ) as check_log
                from (
                    select status, error, created_at
                    from public.check_logs
                    where locale_id = locale.id
                    order by created_at desc
                    limit 5
                ) recent
            ) logs on true
            left join lateral (
                select audit_text
                from public.aso_audits
                where app_id = app.id
                order by created_at desc
                limit 1
            ) audit on true
            where app.active = true and locale.active = true
            order by app.package_id, locale.geo
        """
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()

        data: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            info = tracked_info_from_row(
                row.get("package_id"),
                row.get("geo"),
                row.get("chat_id"),
                title=row.get("title"),
                summary=row.get("summary"),
                description=row.get("description"),
                icon=row.get("icon"),
                header_image=row.get("header_image"),
                screenshots=_json_cell(row.get("screenshots")),
                check_log=_json_cell(row.get("check_log")),
                ai_audit=row.get("ai_audit"),
            )
            if info:
                key = info.pop("_storage_key", storage_key(info))
                data[key] = info
        return data

    def upsert_user(self, name: str, chat_id: Any) -> None:
        query = """
            insert into public.monitor_users (name, chat_id)
            values (%s, %s)
            on conflict (chat_id) do update
            set name = excluded.name
        """
        with self._connect() as conn:
            conn.execute(query, (str(name), _normalize_chat_id(chat_id)))

    def upsert_tracked_info(self, info: Dict[str, Any], *, owner_name: Optional[str] = None) -> Tuple[str, str]:
        package_id = str(info["package_id"]).strip()
        geo = str(info["geo"]).strip()
        chat_id = _normalize_chat_id(info.get("chat_id"))
        name = owner_name or f"User {chat_id}"
        current = info.get("current", {})
        check_log = list(info.get("check_log") or [])
        last_log = check_log[-1] if check_log else {}
        last_checked_at = _parse_minsk_timestamp(last_log.get("time"))
        last_status = last_log.get("status")

        with self._connect() as conn:
            user_row = conn.execute(
                """
                    insert into public.monitor_users (name, chat_id)
                    values (%s, %s)
                    on conflict (chat_id) do update
                    set name = excluded.name
                    returning chat_id
                """,
                (name, chat_id),
            ).fetchone()
            owner_chat_id = user_row["chat_id"]

            app_row = conn.execute(
                """
                    insert into public.tracked_apps (package_id, platform, owner_chat_id, active)
                    values (%s, %s, %s, true)
                    on conflict (package_id, owner_chat_id) do update
                    set platform = excluded.platform,
                        active = true
                    returning id
                """,
                (package_id, _platform_for_package(package_id), owner_chat_id),
            ).fetchone()
            app_id = app_row["id"]

            locale_row = conn.execute(
                """
                    insert into public.tracked_locales (
                        app_id, geo, title, summary, description, icon, header_image,
                        screenshots, last_checked_at, last_status, active
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, true)
                    on conflict (app_id, geo) do update
                    set title = excluded.title,
                        summary = excluded.summary,
                        description = excluded.description,
                        icon = excluded.icon,
                        header_image = excluded.header_image,
                        screenshots = excluded.screenshots,
                        last_checked_at = excluded.last_checked_at,
                        last_status = excluded.last_status,
                        active = true
                    returning id
                """,
                (
                    app_id,
                    geo,
                    current.get("title", ""),
                    current.get("summary", ""),
                    current.get("description", ""),
                    current.get("icon", ""),
                    current.get("header_image", ""),
                    json.dumps(current.get("screenshots", []), ensure_ascii=False),
                    last_checked_at,
                    last_status,
                ),
            ).fetchone()
            locale_id = locale_row["id"]

            conn.execute(
                """
                    insert into public.snapshots (
                        locale_id, title, summary, description, icon, header_image,
                        screenshots, source, captured_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s::jsonb, 'import', now())
                """,
                (
                    locale_id,
                    current.get("title", ""),
                    current.get("summary", ""),
                    current.get("description", ""),
                    current.get("icon", ""),
                    current.get("header_image", ""),
                    json.dumps(current.get("screenshots", []), ensure_ascii=False),
                ),
            )

            if check_log:
                conn.execute("delete from public.check_logs where locale_id = %s", (locale_id,))
                for log_entry in check_log[-5:]:
                    conn.execute(
                        """
                            insert into public.check_logs (locale_id, status, error, created_at)
                            values (%s, %s, %s, %s)
                        """,
                        (
                            locale_id,
                            str(log_entry.get("status", "")),
                            log_entry.get("error"),
                            _created_at_from_log(log_entry),
                        ),
                    )

            audit_text = str(info.get("ai_audit") or "").strip()
            if audit_text:
                conn.execute(
                    """
                        insert into public.aso_audits (app_id, audit_text, source)
                        values (%s, %s, 'import')
                    """,
                    (app_id, audit_text),
                )

        return str(app_id), str(locale_id)

    def import_tracked_apps(self, data: Dict[str, Dict[str, Any]], *, users: Dict[str, Any]) -> Dict[str, int]:
        for name, chat_id in users.items():
            self.upsert_user(str(name), chat_id)

        imported = 0
        skipped = 0
        for info in data.values():
            if not info:
                skipped += 1
                continue
            chat_id = _normalize_chat_id(info.get("chat_id"))
            owner_name = _user_name_for_chat_id(chat_id, users)
            self.upsert_tracked_info(info, owner_name=owner_name)
            imported += 1

        return {"users": len(users), "locales": imported, "skipped": skipped}

    def count_rows(self) -> Dict[str, int]:
        tables: Iterable[str] = (
            "monitor_users",
            "tracked_apps",
            "tracked_locales",
            "snapshots",
            "check_logs",
            "aso_audits",
        )
        counts = {}
        with self._connect() as conn:
            for table in tables:
                row = conn.execute(f"select count(*) as count from public.{table}").fetchone()
                counts[table] = int(row["count"])
        return counts
