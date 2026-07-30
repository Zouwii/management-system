"""Re-parse all kb_documents content using the fixed parser.

Reads raw_json from kb_documents, runs parse_document(), updates content.
No DingTalk API calls — fully offline.
"""

import json
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, '/home/jz/zhr/tb_tool_bt/backend')

from ai.knowledge.models import KbDocument
from ai.knowledge.parser import parse_document
from base.db.engine import KbSessionLocal


def reparse_all(batch_size: int = 500):
    db = KbSessionLocal()
    now = datetime.now(timezone.utc)

    total = db.query(KbDocument).filter(
        KbDocument.raw_json.isnot(None),
        KbDocument.raw_json != "",
    ).count()
    print(f"Total documents with raw_json: {total}")

    updated = 0
    errors = 0
    skipped = 0
    offset = 0

    while True:
        docs = db.query(KbDocument).filter(
            KbDocument.raw_json.isnot(None),
            KbDocument.raw_json != "",
        ).limit(batch_size).offset(offset).all()

        if not docs:
            break

        for doc in docs:
            try:
                data = json.loads(doc.raw_json)
                blocks = data.get("data", [])
                if not blocks:
                    skipped += 1
                    continue

                result = parse_document(blocks, "blocks")
                new_content = result.get("markdown", "")

                if doc.content != new_content:
                    doc.content = new_content
                    doc.updated_at = now
                    updated += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  [err] id={doc.id} title={doc.title[:30]}... {e}")

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"  [commit-err] {e}")

        offset += batch_size
        print(f"  processed {offset}/{total} ... updated={updated} errors={errors} skipped={skipped}")

    db.close()
    print(f"\nDone. updated={updated} errors={errors} skipped={skipped} total={total}")


if __name__ == "__main__":
    reparse_all()
