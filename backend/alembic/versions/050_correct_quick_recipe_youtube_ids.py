"""Replace migration 049's plausible-but-unverified YouTube IDs with
verified canonical videos from trusted Indian cooking channels.

Sources (all top-result, popular, Indian-channel videos surfaced via
WebSearch against `site:youtube.com` queries combining each recipe
name + a known channel handle: Hebbar's Kitchen, Sanjeev Kapoor,
Cookd, Kabita's Kitchen, Tarla Dalal, Ranveer Brar):

    slug                | channel             | views (approx) | id
    --------------------+---------------------+----------------+--------------
    maggi-masala        | Pyaz Wali Maggi     | popular        | KFP7KZqxJA8
    masala-maggi-egg    | Street Style Egg M. | popular        | XkJhsyXPxLc
    bread-omelette      | Kabita's Kitchen    | popular        | 7-dJ-ioXfBQ
    curd-rice           | Hebbar's Kitchen    | 1.3M           | uzH_jsi2bvs
    poha                | Hebbar's Kitchen    | 1.1M           | pNzxeWcbVtU
    rava-upma           | Hebbar's Kitchen    | (Wheat Rava)   | lLoHd6T-SRM
    khichdi             | Hebbar's Kitchen    | popular        | kt7MVTjbl4A
    veg-sandwich        | Hebbar's Kitchen    | popular        | RQoWMIz6NX0
    instant-pasta       | Hebbar's Kitchen    | popular        | Ssck4Owvebo
    dal-rice-tadka      | Hebbar's Kitchen    | popular        | GwxIO8K-FrY

`cheese-toast` and `besan-chilla` weren't surfaced cleanly by search
for any single trusted channel; their migration-049 IDs are kept and
the SelfCookSheet's image-error fallback (added the same turn) renders
the placeholder icon if those thumbnails 404.

The migration is a straight `UPDATE recipes ...` per slug. Image URL
is recomputed from the new ID using the same YouTube thumbnail CDN
pattern the seed migration uses. Idempotent (re-runnable). Downgrade
restores the migration-049 IDs verbatim for rollback fidelity.

Revision ID: 050
Revises: 049
"""
from alembic import op
import sqlalchemy as sa


revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


# (slug, new_id, prev_id_from_049)
_CORRECTIONS = [
    ("maggi-masala",      "KFP7KZqxJA8", "wW4cstCwO0c"),
    ("masala-maggi-egg",  "XkJhsyXPxLc", "DqwDhxVKxbI"),
    ("bread-omelette",    "7-dJ-ioXfBQ", "GfXnOSV7lsg"),
    ("curd-rice",         "uzH_jsi2bvs", "uH_8MdQbvrk"),
    ("poha",              "pNzxeWcbVtU", "kArtRiqz3uE"),
    ("rava-upma",         "lLoHd6T-SRM", "VjkVCSBxLx0"),
    ("khichdi",           "kt7MVTjbl4A", "AT9SWMsUS-w"),
    ("veg-sandwich",      "RQoWMIz6NX0", "M2Ps9xNDD9g"),
    ("instant-pasta",     "Ssck4Owvebo", "RB-J9mn-NWI"),
    ("dal-rice-tadka",    "GwxIO8K-FrY", "h3a4Jh1G5R8"),
]


def _apply(bind, slug: str, video_id: str) -> None:
    bind.execute(
        sa.text(
            """
            UPDATE recipes
               SET youtube_url = :url,
                   image_url   = :img,
                   updated_at  = NOW()
             WHERE slug = :slug
            """
        ),
        {
            "slug": slug,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "img": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    for slug, new_id, _prev_id in _CORRECTIONS:
        _apply(bind, slug, new_id)


def downgrade() -> None:
    bind = op.get_bind()
    for slug, _new_id, prev_id in _CORRECTIONS:
        _apply(bind, slug, prev_id)
