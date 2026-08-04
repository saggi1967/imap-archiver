from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("imap-archiver")
except PackageNotFoundError:  # nicht installiert (z. B. direkt aus dem Quellbaum)
    __version__ = "2.5.0.0"
