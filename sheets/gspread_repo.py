import json
from typing import Any, Dict, Iterator, List, Optional, Tuple

import gspread

from core.config import Settings
from sheets.serialization import parse_json_list


class GspreadAppsRepository:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._worksheet: Any = None
        self._headers: List[str] = []

    def open(self) -> None:
        if not self._settings.spreadsheet_url:
            raise ValueError("SPREADSHEET_URL не задан (env или Settings)")
        if not self._settings.gcp_service_account_json:
            raise ValueError("GCP_SERVICE_ACCOUNT_JSON не задан")

        service_account_info = json.loads(self._settings.gcp_service_account_json)
        gc = gspread.service_account_from_dict(service_account_info)
        sh = gc.open_by_url(self._settings.spreadsheet_url)
        self._worksheet = sh.get_worksheet(0)
        self._headers = self._worksheet.row_values(1)

    @property
    def headers(self) -> List[str]:
        return self._headers

    def iter_rows(self) -> Iterator[Tuple[int, Dict[str, str]]]:
        if self._worksheet is None:
            raise RuntimeError("Repository not opened. Call open() first.")

        all_rows = self._worksheet.get_all_values()
        for row_index, row_values in enumerate(all_rows[1:], start=2):
            row = {
                self._headers[j]: (row_values[j] if j < len(row_values) else "")
                for j in range(len(self._headers))
            }
            yield row_index, row

    def update_row(self, row_index: int, row: Dict[str, str]) -> None:
        if self._worksheet is None:
            raise RuntimeError("Repository not opened. Call open() first.")
        new_row_list = [row.get(h, "") for h in self._headers]
        range_name = f"A{row_index}:{gspread.utils.rowcol_to_a1(row_index, len(self._headers))}"
        self._worksheet.update(range_name, [new_row_list])

    @staticmethod
    def parse_row_lists(row: Dict[str, str]) -> Tuple[List, List, List]:
        return (
            parse_json_list(row.get("screenshots", "[]")),
            parse_json_list(row.get("history", "[]")),
            parse_json_list(row.get("check_log", "[]")),
        )
