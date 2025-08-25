import hashlib


def make_cache_key(*args):
    raw_key = ":".join(arg or "" for arg in args)
    return hashlib.sha1(raw_key.encode("utf-8")).hexdigest()
