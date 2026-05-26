import json
from typing import Any, Callable, Dict, Optional

from core.config import Settings
from sheets.serialization import storage_key, tracked_info_from_row


ConnectionFactory = Callable[[str], Any]


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
