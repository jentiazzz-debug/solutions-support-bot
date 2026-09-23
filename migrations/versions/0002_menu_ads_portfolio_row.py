"""Главное меню: «Реклама» и «Наше портфолио» вместе во втором ряду.

Стартовое меню записывается в БД один раз, поэтому в уже запущенных
ботах раскладку нужно поправить миграцией:
    О нас
    Реклама | Наше портфолио
    Поддержка
    (свои кнопки-ссылки — ниже, в прежнем порядке)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORDER = ("about", "ads", "portfolio", "support")
HALF = ("ads", "portfolio")


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, key FROM menu_buttons ORDER BY position, id")
    ).all()
    builtin = sorted((r for r in rows if r.key in ORDER), key=lambda r: ORDER.index(r.key))
    others = [r for r in rows if r.key not in ORDER]
    for position, row in enumerate([*builtin, *others], start=1):
        width = 2 if row.key in HALF else (1 if row.key in ORDER else None)
        if width is None:
            conn.execute(
                sa.text("UPDATE menu_buttons SET position = :p WHERE id = :id"),
                {"p": position, "id": row.id},
            )
        else:
            conn.execute(
                sa.text("UPDATE menu_buttons SET position = :p, row_width = :w WHERE id = :id"),
                {"p": position, "w": width, "id": row.id},
            )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE menu_buttons SET row_width = 1 WHERE key IN ('ads', 'portfolio')")
    )
