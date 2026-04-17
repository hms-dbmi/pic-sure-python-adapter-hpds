from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from picsure.errors import PicSureValidationError


@dataclass(frozen=True)
class PlatformConfig:
    """Connection details for a known PIC-SURE deployment."""

    url: str
    resource_uuid: str
    label: str
    include_consents: bool
    requires_auth: bool


@dataclass(frozen=True)
class PlatformInfo:
    """Resolved platform connection details."""

    url: str
    resource_uuid: str | None = None
    include_consents: bool = False
    # Default True for custom URLs — safer to assume a token is needed
    # unless the caller explicitly opts out with ``requires_auth=False``.
    requires_auth: bool = True


class Platform(Enum):
    """Known PIC-SURE deployment platforms.

    Each member stores a :class:`PlatformConfig`.  BDC Authorized and
    BDC Open share a domain and are distinguished by resource UUID.
    ``include_consents`` controls whether dictionary-api requests must
    carry the user's consent list; ``requires_auth`` controls whether
    the connection needs a PIC-SURE token at all.

    Pass a member to :func:`picsure.connect` to connect to a known
    platform, or pass a custom URL string for unlisted deployments.
    """

    BDC_AUTHORIZED = PlatformConfig(
        url="https://picsure.biodatacatalyst.nhlbi.nih.gov",
        resource_uuid="02e23f52-f354-4e8b-992c-d37c8b9ba140",
        label="BDC Authorized",
        include_consents=True,
        requires_auth=True,
    )
    BDC_OPEN = PlatformConfig(
        url="https://picsure.biodatacatalyst.nhlbi.nih.gov",
        resource_uuid="ac004461-1b47-4832-80e2-22a4aecabe39",
        label="BDC Open",
        include_consents=False,
        requires_auth=False,
    )
    BDC_DEV_AUTHORIZED = PlatformConfig(
        url="https://dev.picsure.biodatacatalyst.nhlbi.nih.gov",
        resource_uuid="02e23f52-f354-4e8b-992c-d37c8b9ba140",
        label="BDC Authorized",
        include_consents=True,
        requires_auth=True,
    )
    BDC_DEV_OPEN = PlatformConfig(
        url="https://dev.picsure.biodatacatalyst.nhlbi.nih.gov",
        resource_uuid="ac004461-1b47-4832-80e2-22a4aecabe39",
        label="BDC Open",
        include_consents=False,
        requires_auth=False,
    )
    BDC_PREDEV_AUTHORIZED = PlatformConfig(
        url="https://predev.picsure.biodatacatalyst.nhlbi.nih.gov",
        resource_uuid="02e23f52-f354-4e8b-992c-d37c8b9ba140",
        label="BDC Authorized",
        include_consents=True,
        requires_auth=True,
    )
    BDC_PREDEV_OPEN = PlatformConfig(
        url="https://predev.picsure.biodatacatalyst.nhlbi.nih.gov",
        resource_uuid="ac004461-1b47-4832-80e2-22a4aecabe39",
        label="BDC Open",
        include_consents=False,
        requires_auth=False,
    )
    NHANES_AUTHORIZED = PlatformConfig(
        url="https://nhanes.hms.harvard.edu/",
        resource_uuid="",
        label="Nhanes Authorized",
        include_consents=False,
        requires_auth=True,
    )
    NHANES_OPEN = PlatformConfig(
        url="https://nhanes.hms.harvard.edu/",
        resource_uuid="ded89b08-faa9-435c-b7c4-55b81922ee5f",
        label="Nhanes Open",
        include_consents=False,
        requires_auth=False,
    )
    AIM_AHEAD = PlatformConfig(
        url="https://picsure.aim-ahead.net",
        resource_uuid="REPLACE-ME-aim-ahead-resource-uuid",
        label="AIM-AHEAD",
        include_consents=True,
        requires_auth=True,
    )

    @property
    def url(self) -> str:
        return self.value.url

    @property
    def resource_uuid(self) -> str:
        return self.value.resource_uuid

    @property
    def label(self) -> str:
        return self.value.label

    @property
    def include_consents(self) -> bool:
        return self.value.include_consents

    @property
    def requires_auth(self) -> bool:
        return self.value.requires_auth


def resolve_platform(
    platform: Platform | str,
    *,
    include_consents: bool | None = None,
    requires_auth: bool | None = None,
) -> PlatformInfo:
    """Resolve a platform enum or custom URL to connection details.

    Args:
        platform: A :class:`Platform` enum member or a full URL
            (e.g. ``"https://my-picsure.example.com"``).
        include_consents: When ``platform`` is a custom URL, overrides
            the default of ``False``.  When ``platform`` is a
            :class:`Platform` member, overrides the member's own flag.
        requires_auth: Overrides the auth requirement.  Custom URLs
            default to ``True`` (a token is required); :class:`Platform`
            members default to their own flag.

    Returns:
        A :class:`PlatformInfo` with the base URL, optional resource
        UUID, consent policy, and auth requirement.

    Raises:
        PicSureValidationError: If the value is not a ``Platform`` member
            and does not look like a URL.
    """
    if isinstance(platform, Platform):
        resolved_consents = (
            include_consents
            if include_consents is not None
            else platform.include_consents
        )
        resolved_auth = (
            requires_auth
            if requires_auth is not None
            else platform.requires_auth
        )
        return PlatformInfo(
            url=platform.url,
            resource_uuid=platform.resource_uuid,
            include_consents=resolved_consents,
            requires_auth=resolved_auth,
        )

    if isinstance(platform, str) and platform.startswith(("http://", "https://")):
        return PlatformInfo(
            url=platform.rstrip("/"),
            include_consents=bool(include_consents),
            requires_auth=True if requires_auth is None else requires_auth,
        )

    valid = ", ".join(p.label for p in Platform)
    raise PicSureValidationError(
        f"'{platform}' is not a recognized platform. "
        f"Valid platforms: {valid}. "
        "You can also pass a Platform enum member or a full URL "
        "(e.g. 'https://my-picsure.example.com')."
    )
