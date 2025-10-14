class UserInputError(Exception):
    """Raised for validation errors that should be shown to the user."""


class RateLimitError(Exception):
    """Raised when a user exceeds a command's rate limit."""
