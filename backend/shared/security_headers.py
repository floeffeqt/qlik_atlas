from fastapi import Response


def apply_security_headers(response: Response, connect_src: str) -> None:
    csp = " ".join(
        [
            "default-src 'self';",
            f"connect-src 'self' {connect_src};",
            "img-src 'self' data:;",
            "script-src 'self';",
            "style-src 'self' 'unsafe-inline';",
        ]
    )
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
