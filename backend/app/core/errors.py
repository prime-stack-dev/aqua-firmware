class AppError(Exception):
    """An expected failure that the API reports to the caller."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def not_found(what: str = "Resource") -> AppError:
    # Also used for another customer's data, so its existence is not revealed.
    return AppError(404, f"{what} not found")


def forbidden(detail: str = "Not allowed") -> AppError:
    return AppError(403, detail)


def unauthorized(detail: str = "Invalid credentials") -> AppError:
    return AppError(401, detail)
