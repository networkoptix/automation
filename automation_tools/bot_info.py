## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import os


def revision():
    return os.environ.get("BOT_REVISION", "unknown")


def name():
    return os.environ.get("BOT_NAME", "unknown")
