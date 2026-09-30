"""Exceptions used by EmbedUtils."""


class EmbedUtilsException(Exception):
    """Base class for EmbedUtils exceptions."""


class EmbedNotFound(EmbedUtilsException):
    """Raised when an embed isn't found on a message or in storage."""


class EmbedFileError(EmbedUtilsException):
    """Raised when an uploaded embed file is missing or invalid."""


class EmbedLimitReached(EmbedUtilsException):
    """Raised when the stored embed limit has been reached."""


class EmbedConversionError(EmbedUtilsException):
    def __init__(self, error_type: str, error: Exception):
        self.error_type = error_type
        self.error = error
        super().__init__(error)
