from picsure.errors import PicSureValidationError

# PLACEHOLDER URLs — replace with real deployment URLs when available.
_PLATFORMS: dict[str, str] = {
    "bdc authorized": "https://picsure.biodatacatalyst.nhlbi.nih.gov",
    "bdc open": "https://openpicsure.biodatacatalyst.nhlbi.nih.gov",
    "demo": "https://demo.picsure.biodatacatalyst.nhlbi.nih.gov",
    "aim-ahead": "https://picsure.aim-ahead.net",
}

_DISPLAY_NAMES: list[str] = [
    "BDC Authorized",
    "BDC Open",
    "Demo",
    "AIM-AHEAD",
]


def resolve_platform_url(platform: str) -> str:
    """Resolve a platform name or URL to a base URL.

    Args:
        platform: A named platform (e.g. "BDC Authorized") or a full URL
            (e.g. "https://my-picsure.example.com").

    Returns:
        The resolved base URL with no trailing slash.

    Raises:
        PicSureValidationError: If the platform name is not recognized and
            does not look like a URL.
    """
    if platform.startswith(("http://", "https://")):
        return platform.rstrip("/")

    key = platform.lower().strip()
    if key in _PLATFORMS:
        return _PLATFORMS[key]

    valid = ", ".join(_DISPLAY_NAMES)
    raise PicSureValidationError(
        f"'{platform}' is not a recognized platform. "
        f"Valid platforms: {valid}. "
        "You can also pass a full URL (e.g. 'https://my-picsure.example.com')."
    )
