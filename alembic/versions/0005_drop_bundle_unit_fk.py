"""Drop the FK on provenance_bundles.translation_unit_id — it's a polymorphic
subject id (TranslationUnit OR, since Phase 4, ImageTranslationUnit), not a
reference to one specific table.

Revision ID: 0005_drop_bundle_unit_fk
Revises: 0004_image_assets
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_drop_bundle_unit_fk"
down_revision: Union[str, None] = "0004_image_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "provenance_bundles_translation_unit_id_fkey", "provenance_bundles", type_="foreignkey"
    )


def downgrade() -> None:
    op.create_foreign_key(
        "provenance_bundles_translation_unit_id_fkey", "provenance_bundles",
        "translation_units", ["translation_unit_id"], ["id"],
    )
