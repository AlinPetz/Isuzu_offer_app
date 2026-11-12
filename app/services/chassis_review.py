"""Local, append-only approvals for a specific set of chassis evidence."""
import argparse
from datetime import datetime, timezone
import json

from app.config import BASE_DIR, WORKBOOK_PATH
from app.repositories.excel_repository import ExcelRepository
from app.services.chassis_catalog import ChassisCatalog


APPROVAL_LOG = BASE_DIR / "data" / "chassis_review_approvals.jsonl"


def load_approvals(path=None):
    path = APPROVAL_LOG if path is None else path
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()
    approved = set()
    for line in lines:
        try:
            entry = json.loads(line)
            if all(isinstance(entry[key], str) and entry[key].strip()
                   for key in ("fingerprint", "chassis_id", "reviewer", "evidence", "approved_at")):
                approved.add(entry["fingerprint"])
        except (ValueError, KeyError, TypeError):
            continue
    return approved


def approve_review(catalog, chassis_id, reviewer, evidence, path=None):
    path = APPROVAL_LOG if path is None else path
    if not reviewer.strip() or not evidence.strip():
        raise ValueError("Reviewer and evidence are required.")
    matches = catalog.by_id.get(chassis_id, [])
    if len(matches) != 1:
        raise ValueError("Approval requires a unique chassis ID.")
    record = catalog.by_row[matches[0]["excel_row"]]
    if record["errors"] or not record["reviews"]:
        raise ValueError("Approval requires an open manual review and no structural errors.")
    entry = {
        "chassis_id": chassis_id,
        "fingerprint": record["review_fingerprint"],
        "reviewer": reviewer.strip(),
        "evidence": evidence.strip(),
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chassis_id")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--evidence", required=True, help="Reference for verified gearbox and PTO data")
    args = parser.parse_args()
    try:
        catalog = ChassisCatalog(ExcelRepository(WORKBOOK_PATH).load_chassis(), load_approvals())
        approve_review(catalog, args.chassis_id, args.reviewer, args.evidence)
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
    print(f"Approval recorded for {args.chassis_id} in {APPROVAL_LOG}")


if __name__ == "__main__":
    main()
