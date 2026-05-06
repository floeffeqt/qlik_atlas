from urllib.parse import quote


def url_encode_qri(qri: str) -> str:
    return quote(qri, safe="")
