"""Readiness checks used by setup.ps1 (kept in Python to avoid shell quoting).

    python -m app.status db        exit 0 when Exasol accepts connections, else exit 2
    python -m app.status results   print READY / DATA / EMPTY (exit 0), or exit 2 when Exasol is unreachable

An unreachable database is never reported as "no results", so a slow start can
never trigger a data reload.
"""
import sys

from app import db


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "db"
    try:
        conn = db.connect(fetch_dict=False)
    except Exception as e:
        print(f"UNREACHABLE: {str(e).splitlines()[0] if str(e) else e}", file=sys.stderr)
        sys.exit(2)
    try:
        if what == "results":
            names = {r[0] for r in conn.execute(
                "SELECT TABLE_NAME FROM EXA_ALL_TABLES WHERE TABLE_SCHEMA = {s} "
                "AND TABLE_NAME IN ('CASE_SUMMARY', 'TRANSACTIONS')", {"s": db.SCHEMA}).fetchall()}
            # READY: results exist. DATA: data loaded, analysis missing. EMPTY: nothing loaded.
            print("READY" if "CASE_SUMMARY" in names else "DATA" if "TRANSACTIONS" in names else "EMPTY")
        else:
            print("UP")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
