def format_datetime(value):
    """Firestore timestamps, datetime, or ISO strings → ISO string or None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
