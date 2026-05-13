"""Engine — Anthropic protocol primitives shared across the entire gateway."""

from .content import extract_text, get_attr, get_type
from .conversion import MessageConverter, build_openai_body
from .errors import append_rid, error_message
from .sse import BlockManager, StreamEvent, map_finish_reason
from .thinking import Chunk, ChunkKind, ThinkParser
from .tokens import count_tokens
from .tools import ToolParser

__all__ = [
    "BlockManager",
    "Chunk",
    "ChunkKind",
    "MessageConverter",
    "StreamEvent",
    "ThinkParser",
    "ToolParser",
    "append_rid",
    "build_openai_body",
    "count_tokens",
    "error_message",
    "extract_text",
    "get_attr",
    "get_type",
    "map_finish_reason",
]
