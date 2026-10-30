from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path


STATUS = {
    "pending": "Bereit",
    "measured": "Gemessen",
    "uncertain": "Bitte prüfen",
    "unusable": "Nicht auswertbar",
    "error": "Dateifehler",
}
REASONS = {
    "quality_filter": "Pegel oder Umgebung sind nicht ausreichend erkennbar.",
    "clear_zero_context": "Die Umgebung wurde als eindeutig schneefrei erkannt.",
    "ambiguous_zero_context": "Es ist nicht eindeutig erkennbar, ob Schnee liegt.",
    "geometric_models_disagree": "Die Schätzungen widersprechen sich. Bitte am Originalbild prüfen.",
    "height_disagreement": "Die Schneehöhe lässt sich nicht ausreichend sicher bestimmen.",
    "positive_peg_model": "Die Schneehöhe wurde aus dem Pegelprofil bestimmt.",
    "calibrated_direct_geometric_specialist": "Pegelgeometrie und Höhenmodell stimmen überein.",
    "calibrated_high_range_specialist": "Schneegrenze und Höhenmodell stimmen überein.",
    "calibrated_low_range_specialist": "Der niedrige Schneepegel wurde anhand der Kalibrierung bestimmt.",
}


def explanation(result: dict | None) -> str:
    if not result:
        return "Dieses Bild ist für die Analyse bereit."
    if result["status"] == "error":
        return result["reason"]
    return REASONS.get(result["reason"], "Bitte prüfen Sie das Originalbild.")


def height_text(result: dict | None) -> str:
    if not result or result.get("snow_height_cm") is None:
        return "—"
    return f'{result["snow_height_cm"]:g}'.replace(".", ",")


class Library:
    """Persist file references and results; never copy or change source images."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # sqlite3's default 5-second lock wait only applies to database writes.
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS images (path TEXT PRIMARY KEY, result TEXT)")
        self.rows = [
            {"path": p, "result": json.loads(r) if r else None}
            for p, r in self.connection.execute("SELECT path, result FROM images ORDER BY rowid")
        ]

    def add(self, paths: list[Path]) -> int:
        known = {row["path"] for row in self.rows}
        additions = []
        for path in paths:
            full = str(path.resolve())
            if full not in known:
                additions.append({"path": full, "result": None})
                known.add(full)
        with self.connection:
            self.connection.executemany("INSERT INTO images VALUES (?, NULL)", [(r["path"],) for r in additions])
        self.rows.extend(additions)
        return len(additions)

    def save_result(self, index: int, result: dict) -> None:
        row = self.rows[index]
        with self.connection:
            self.connection.execute(
                "UPDATE images SET result=? WHERE path=?",
                (json.dumps(result, ensure_ascii=False), row["path"]),
            )
        row["result"] = result

    def clear(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM images")
        self.rows.clear()

    def close(self) -> None:
        self.connection.close()


def export_csv(path: Path, rows: list[dict]) -> None:
    # UTF-8 BOM, semicolon and decimal comma work with German Excel.
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Bilddatei", "Dateipfad", "Status", "Schneehöhe (cm)", "Hinweis"])
        for row in rows:
            result = row["result"]
            # A camera file name is untrusted spreadsheet content.
            name = Path(row["path"]).name
            if name.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
                name = "'" + name
            writer.writerow([
                name, row["path"], STATUS[result["status"] if result else "pending"],
                height_text(result) if result and result.get("snow_height_cm") is not None else "",
                explanation(result),
            ])
