## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

def test_pattern_processing():
    from nx_lint.config import process_pattern

    assert process_pattern("foo") == "**/foo"
    assert process_pattern("foo/bar") == "**/foo/bar"
    assert process_pattern("/foo") == "foo"
    assert process_pattern("/foo/bar") == "foo/bar"
    assert process_pattern("**/foo") == "**/foo"
