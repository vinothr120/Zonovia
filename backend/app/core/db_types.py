from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# Renders as JSONB (indexable, binary-stored) on Postgres, plain JSON elsewhere — so the
# same models build a SQLite schema for fast unit tests without losing JSONB on Postgres.
#
# NOTE: SchoolAssist's db_types.py also defines an `EncryptedString` TypeDecorator backed by
# app/core/crypto.py (Fernet field-level encryption). Zonovia's Phase 0 has no caller for
# field-level encryption yet (per the implementation plan's excluded-scope list), so
# core/crypto.py is deliberately not scaffolded and EncryptedString is not ported — add both
# together, the first time a real column needs them.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")
