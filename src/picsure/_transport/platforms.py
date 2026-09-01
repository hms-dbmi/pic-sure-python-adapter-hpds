from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from picsure.errors import PicSureValidationError


@dataclass(frozen=True)
class PlatformConfig:
    """Connection details for a known PIC-SURE deployment."""

    url: str
    label: str
    include_consents: bool
    requires_auth: bool
    supports_genomic: bool


@dataclass(frozen=True)
class PlatformInfo:
    """Resolved platform connection details."""

    url: str
    include_consents: bool = False
    # Default True for custom URLs — safer to assume a token is needed
    # unless the caller explicitly opts out with ``requires_auth=False``.
    requires_auth: bool = True
    supports_genomic: bool = False


class Platform(Enum):
    """Known PIC-SURE deployment platforms.

    Each member stores a :class:`PlatformConfig`.  BDC Authorized and BDC
    Open share a domain; they are distinguished by which HPDS the gateway
    routes to — the ``/hpds/auth`` vs ``/hpds/open`` path — not by a
    resource UUID.  ``include_consents`` controls whether dictionary-api
    requests must carry the user's consent list; ``requires_auth``
    controls whether the connection needs a PIC-SURE token at all.

    Pass a member to :func:`picsure.connect` to connect to a known
    platform, or pass a custom URL string for unlisted deployments.
    """

    BDC_AUTHORIZED = PlatformConfig(
        url="https://picsure.biodatacatalyst.nhlbi.nih.gov",
        label="BDC Authorized",
        include_consents=True,
        requires_auth=True,
        supports_genomic=True,
    )
    BDC_OPEN = PlatformConfig(
        url="https://picsure.biodatacatalyst.nhlbi.nih.gov",
        label="BDC Open",
        include_consents=False,
        requires_auth=False,
        supports_genomic=False,
    )
    BDC_DEV_AUTHORIZED = PlatformConfig(
        url="https://dev.picsure.biodatacatalyst.nhlbi.nih.gov",
        label="BDC Authorized",
        include_consents=True,
        requires_auth=True,
        supports_genomic=True,
    )
    BDC_DEV_OPEN = PlatformConfig(
        url="https://dev.picsure.biodatacatalyst.nhlbi.nih.gov",
        label="BDC Open",
        include_consents=False,
        requires_auth=False,
        supports_genomic=False,
    )
    BDC_PREDEV_AUTHORIZED = PlatformConfig(
        url="https://predev.picsure.biodatacatalyst.nhlbi.nih.gov",
        label="BDC Authorized",
        include_consents=True,
        requires_auth=True,
        supports_genomic=True,
    )
    BDC_PREDEV_OPEN = PlatformConfig(
        url="https://predev.picsure.biodatacatalyst.nhlbi.nih.gov",
        label="BDC Open",
        include_consents=False,
        requires_auth=False,
        supports_genomic=False,
    )
    NHANES_AUTHORIZED = PlatformConfig(
        url="https://nhanes.hms.harvard.edu/",
        label="Nhanes Authorized",
        include_consents=False,
        requires_auth=True,
        supports_genomic=True,
    )
    NHANES_OPEN = PlatformConfig(
        url="https://nhanes.hms.harvard.edu/",
        label="Nhanes Open",
        include_consents=False,
        requires_auth=False,
        supports_genomic=False,
    )

    @property
    def url(self) -> str:
        return self.value.url

    @property
    def label(self) -> str:
        return self.value.label

    @property
    def include_consents(self) -> bool:
        return self.value.include_consents

    @property
    def requires_auth(self) -> bool:
        return self.value.requires_auth

    @property
    def supports_genomic(self) -> bool:
        return self.value.supports_genomic


def resolve_platform(
    platform: Platform | str,
    *,
    include_consents: bool | None = None,
    requires_auth: bool | None = None,
    supports_genomic: bool | None = None,
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
        supports_genomic: Overrides genomic support.  Custom URLs
            default to ``False``; :class:`Platform` members default to
            their own flag.

    Returns:
        A :class:`PlatformInfo` with the base URL, consent policy, auth
        requirement, and genomic support flag.

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
            requires_auth if requires_auth is not None else platform.requires_auth
        )
        resolved_genomic = (
            supports_genomic
            if supports_genomic is not None
            else platform.supports_genomic
        )
        return PlatformInfo(
            url=platform.url,
            include_consents=resolved_consents,
            requires_auth=resolved_auth,
            supports_genomic=resolved_genomic,
        )

    if isinstance(platform, str) and platform.startswith(("http://", "https://")):
        return PlatformInfo(
            url=platform.rstrip("/"),
            include_consents=bool(include_consents),
            requires_auth=True if requires_auth is None else requires_auth,
            supports_genomic=bool(supports_genomic),
        )

    valid = ", ".join(f"Platform.{p.name}" for p in Platform)
    raise PicSureValidationError(
        f"{platform!r} is not a recognized platform. "
        f"Pass a Platform enum member (one of: {valid}) or a full URL "
        "string (e.g. 'https://my-picsure.example.com')."
    )
