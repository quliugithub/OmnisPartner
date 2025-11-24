"""AlertManager service exceptions."""


class MsgSendException(RuntimeError):
    """Raised when a provider or rule blocks message delivery."""

    pass
