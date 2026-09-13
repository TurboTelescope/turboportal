__all__ = ["PhotometryCutoutRequest"]

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from baselayer.app.models import AccessibleIfRelatedRowsAreAccessible, Base


class PhotometryCutoutRequest(Base):
    """A pending or failed request for the cutout behind one photometry point."""

    __tablename__ = "photometry_cutout_requests"

    create = read = update = delete = AccessibleIfRelatedRowsAreAccessible(
        photometry="read"
    )

    index_created_at = False

    photometry_id = sa.Column(
        sa.ForeignKey("photometry.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        doc="Photometry point whose cutout is requested.",
    )
    photometry = relationship("Photometry", doc="The requested Photometry point.")
    requester_id = sa.Column(
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="ID of the User who requested the cutout.",
    )
    requester = relationship("User", doc="The User who requested the cutout.")
    status = sa.Column(
        sa.String(),
        nullable=False,
        default="pending",
        index=True,
        doc="pending or failed; a made cutout removes its request.",
    )
    error = sa.Column(
        sa.String(), nullable=True, doc="Why the cutout could not be made."
    )
