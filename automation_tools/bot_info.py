import os


def revision():
    return os.environ.get("BOT_REVISION", "unknown")


def name():
    return os.environ.get("BOT_NAME", "unknown")
