"""Utility helpers used across modules."""


def format_number(n: int) -> str:
    """Format large numbers with commas."""
    return f"{n:,}"


def trunc_text(text: str, max_len: int = 4000) -> str:
    """Truncate text to max_len characters with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def escape_md(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)


def get_user_display(user) -> str:
    """Get a display name from a Pyrogram user object."""
    if not user:
        return "Unknown"
    name = user.first_name or ""
    if user.last_name:
        name += f" {user.last_name}"
    if user.username:
        name += f" (@{user.username})"
    return name.strip() or "Unknown"


def calculate_uptime(start_time) -> str:
    """Calculate human-readable uptime from a start datetime."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    delta = now - start_time
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)
