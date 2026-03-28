"""CloudFront URL signing utility."""

from datetime import datetime, timedelta, timezone

from app.core.config import settings


def sign_cloudfront_url(url: str, expiry_seconds: int = 3600) -> str:
    """
    Sign a CloudFront URL using RSA key pair.
    Requires cryptography package and a configured private key.
    """
    if not settings.CLOUDFRONT_PRIVATE_KEY_PATH or not settings.CLOUDFRONT_KEY_PAIR_ID:
        # In development, return unsigned URL
        return url

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    import base64
    import json

    expire_time = datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)
    epoch_expiry = int(expire_time.timestamp())

    policy = json.dumps({
        "Statement": [{
            "Resource": url,
            "Condition": {
                "DateLessThan": {"AWS:EpochTime": epoch_expiry}
            }
        }]
    }).replace(" ", "")

    with open(settings.CLOUDFRONT_PRIVATE_KEY_PATH, "rb") as key_file:
        private_key = serialization.load_pem_private_key(key_file.read(), password=None)

    signature = private_key.sign(policy.encode(), padding.PKCS1v15(), hashes.SHA1())
    encoded_sig = base64.b64encode(signature).decode().replace("+", "-").replace("=", "_").replace("/", "~")
    encoded_policy = base64.b64encode(policy.encode()).decode().replace("+", "-").replace("=", "_").replace("/", "~")

    separator = "&" if "?" in url else "?"
    return f"{url}{separator}Policy={encoded_policy}&Signature={encoded_sig}&Key-Pair-Id={settings.CLOUDFRONT_KEY_PAIR_ID}"
