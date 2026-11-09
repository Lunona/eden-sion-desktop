def clamp_value(value, lower, upper):
    """Clamp a scalar rig parameter with ordered bounds."""
    value = float(value)
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value
