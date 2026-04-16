from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from picsure.errors import PicSureValidationError


@dataclass(frozen=True)
class PlatformInfo:
    """Resolved platform connection details."""

    url: str
    resource_uuid: str | None = None


class Platform(Enum):
    """Known PIC-SURE deployment platforms.

    Each member stores ``(url, resource_uuid, label)``.  BDC Authorized
    and BDC Open share a domain and are distinguished by resource UUID.

    Pass a member to :func:`picsure.connect` to connect to a known
    platform, or pass a custom URL string for unlisted deployments.
    """

    BDC_AUTHORIZED = (
        "https://picsure.biodatacatalyst.nhlbi.nih.gov",
        "02e23f52-f354-4e8b-992c-d37c8b9ba140",
        "BDC Authorized",
    )
    BDC_OPEN = (
        "https://picsure.biodatacatalyst.nhlbi.nih.gov",
        "ac004461-1b47-4832-80e2-22a4aecabe39",
        "BDC Open",
    )
    DEMO = (
        "https://demo.picsure.biodatacatalyst.nhlbi.nih.gov",
        "REPLACE-ME-demo-resource-uuid",
        "Demo",
    )
    AIM_AHEAD = (
        "https://picsure.aim-ahead.net",
        "REPLACE-ME-aim-ahead-resource-uuid",
        "AIM-AHEAD",
    )

    @property
    def url(self) -> str:
        return self.value[0]

    @property
    def resource_uuid(self) -> str:
        return self.value[1]

    @property
    def label(self) -> str:
        return self.value[2]


def resolve_platform(platform: Platform | str) -> PlatformInfo:
    """Resolve a platform enum or custom URL to connection details.

    Args:
        platform: A :class:`Platform` enum member or a full URL
            (e.g. ``"https://my-picsure.example.com"``).

    Returns:
        A :class:`PlatformInfo` with the base URL and optional resource UUID.

    Raises:
        PicSureValidationError: If the value is not a ``Platform`` member
            and does not look like a URL.
    """
    if isinstance(platform, Platform):
        return PlatformInfo(url=platform.url, resource_uuid=platform.resource_uuid)

    if isinstance(platform, str) and platform.startswith(("http://", "https://")):
        return PlatformInfo(url=platform.rstrip("/"))

    valid = ", ".join(p.label for p in Platform)
    raise PicSureValidationError(
        f"'{platform}' is not a recognized platform. "
        f"Valid platforms: {valid}. "
        "You can also pass a Platform enum member or a full URL "
        "(e.g. 'https://my-picsure.example.com')."
    )
