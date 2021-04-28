OPENSOURCE_FILES = {
    "test_one_bad_file": [{
        "path": "open/bad_file_1.cpp",
        "content": """#include <string>

int blya()
{

}
""",
    }],
    "test_two_bad_files": [{
        "path": "open/bad_file_2.cpp",
        "content": """#include <string>

int shit()
{

}
""",
    }],
    "test_new_file_good_changes": [{
        "path": "open/good_file_1.cpp",
        "content": """// Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

#include <string>

int good_name()
{

}
"""  # noqa

    }],
}
