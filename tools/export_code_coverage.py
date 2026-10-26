"""Export metadata-only profile/rule coverage for engineer review."""
import json
from compliance.governance import profiles, coverage
from compliance.rule_loader import load_all_rules
from compliance.rule_registry import sync_predicate_flags
from database.db import init_db


def export():
    conn = init_db(':memory:')
    try:
        load_all_rules(conn)
        sync_predicate_flags(conn)
        return {'status': 'ENGINEERING_VERIFICATION_PENDING', 'first_verification_target': 'IPC-2024',
                'profiles': [{**p,'rule_coverage':coverage(conn,p['profile_id'])} for p in profiles()],
                'unsupported_rule_domains':['hot_water','tank','pump'],
                'legacy_only_codes':['UPC','BS_EN']}
    finally:
        conn.close()


if __name__ == '__main__':
    print(json.dumps(export(), indent=2, ensure_ascii=True))
