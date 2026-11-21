"""Check the backend settings before a deploy.

    python -m scripts.preflight --production            # exit 1 if anything would break or be exposed
    python -m scripts.preflight --production --strict  # warnings fail too

Run it with the production environment variables loaded (for example after `vercel env pull`).
Nothing is sent anywhere; it only reads the settings.
"""
import argparse
import os
import sys

from app.core.config import get_settings
from app.core.preflight import check


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--production", action="store_true", help="apply the production rules (default: only when VERCEL_ENV/ENVIRONMENT say production)")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args(argv)

    findings = check(get_settings(), os.environ, True if args.production else None)
    for f in findings:
        print(f"{f.level.upper():<8}{f.code:<16}{f.message}")
    errors = sum(f.level == "error" for f in findings)
    warnings = len(findings) - errors
    print(f"\n{errors} error(s), {warnings} warning(s)")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
