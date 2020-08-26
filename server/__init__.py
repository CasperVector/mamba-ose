from functools import wraps

logger = None
config = None
session = None


def verify(f):
    """decorator"""
    @wraps(f)
    def wrapper(*args):
        current = args[-1]
        session.verify(current)
        f(*args)

    return wrapper
