__all__ = ["TurboSourceRequest"]

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql
from sqlalchemy.orm import relationship

from baselayer.app.models import (
    AccessibleIfRelatedRowsAreAccessible,
    AccessibleIfUserMatches,
    Base,
)


class TurboSourceRequest(Base):
    """A request to bring one star from TURBO's own database into SkyPortal as a source."""

    __tablename__ = "turbo_source_requests"

    create = read = AccessibleIfRelatedRowsAreAccessible(allocation="read")
    update = delete = (
        AccessibleIfUserMatches("allocation.group.users")
        | AccessibleIfUserMatches("requester")
    ) & read

    index_created_at = False

    allocation_id = sa.Column(
        sa.ForeignKey("allocations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="TURBO allocation whose forced-photometry worker serves the request.",
    )
    allocation = relationship("Allocation", doc="The TURBO allocation.")
    requester_id = sa.Column(
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="ID of the User who made the request.",
    )
    requester = relationship("User", doc="The User who made the request.")
    star = sa.Column(
        sa.String, nullable=True, doc="TURBO star ID, when asked for by name."
    )
    ra = sa.Column(sa.Float, nullable=True, doc="ICRS Right Ascension [deg].")
    dec = sa.Column(sa.Float, nullable=True, doc="ICRS Declination [deg].")
    radius = sa.Column(
        sa.Float, nullable=False, doc="Search radius around the position [arcsec]."
    )
    group_ids = sa.Column(
        psql.ARRAY(sa.Integer),
        nullable=False,
        doc="Groups the source and its photometry are shared with.",
    )
    status = sa.Column(
        sa.String,
        nullable=False,
        default="pending",
        index=True,
        doc="pending, completed or failed.",
    )
    message = sa.Column(
        sa.String, nullable=True, doc="What was found, or why the request failed."
    )
    obj_id = sa.Column(
        sa.ForeignKey("objs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="ID of the source the request brought in.",
    )
    obj = relationship("Obj", doc="The source the request brought in.")
    n_points = sa.Column(
        sa.Integer, nullable=True, doc="Photometry points sent to SkyPortal."
    )
