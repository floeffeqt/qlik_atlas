from fastapi import Response


def apply_security_headers(response: Response, connect_src: str) -> None:
    csp = " ".join(
        [
            "default-src 'self';",
            f"connect-src 'self' {connect_src};",
            "img-src 'self' data:;",
            "script-src 'self';",
            # 'unsafe-inline' required: frontend uses extensive inline <style> blocks.
            # Removing it would break all pages. Migrate to external CSS to drop this.
            "style-src 'self' 'unsafe-inline';",
        ]
    )
    response.headers["Content-Security-Policy"] = csp
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
