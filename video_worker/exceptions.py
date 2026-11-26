class VideoError(RuntimeError):
    """Base error for video operations."""


class VideoProcessingError(VideoError):
    """FFmpeg or FFprobe could not complete an operation."""


class InvalidSelectionError(ValueError):
    """A selected time range is invalid."""
