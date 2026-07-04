from enum import Enum


class MessageType(Enum):
    INFO = "INFO"
    WARNING = "WARN"
    ERROR = "ERROR"


def write_line(message: str, message_type: MessageType = MessageType.INFO) -> None:
    print(f"[{message_type.value}] {message}")
