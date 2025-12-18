from django import template

register = template.Library()

@register.filter
def indian_comma(value):
    try:
        value = float(value)
    except:
        return value

    # Convert to integer (drop decimals)
    value = int(value)

    s = str(value)

    # If length ≤ 3 → no need to format
    if len(s) <= 3:
        return s

    # Last 3 digits stay together
    last3 = s[-3:]
    rest = s[:-3]

    # Add commas every 2 digits (Indian system)
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    parts.insert(0, rest)

    return ",".join(parts) + "," + last3
