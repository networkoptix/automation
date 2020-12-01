import base64
from dataclasses import dataclass, field

from tests.common_constants import DEFAULT_COMMIT, BAD_OPENSOURCE_COMMIT, FILE_COMMITS_SHA

GOOD_README_RAW_DATA = """# Nx Meta VMP Open Source Components

// Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

---------------------------------------------------------------------------------------------------
"""

BAD_README_RAW_DATA = """# Nx Meta VMP Open Source Components

// Copyrleft 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

-shit fuck blya------------------------------------------------------------------------------------
"""

BAD_README_RAW_DATA_2 = """# Nx Meta VMP Open Source Components

// Copyrleft 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

-shit fuck blya------------------------------------------------------------------------------------

-hanwha
"""


@dataclass
class FileManagerMock():
    commit_files: dict = field(default_factory=lambda: {
        FILE_COMMITS_SHA["good_dontreadme"]: [
            FileManagerMock.ProjectFileMock(
                path="open/dontreadme.md", raw_data=GOOD_README_RAW_DATA),
        ],
        FILE_COMMITS_SHA["bad_dontreadme"]: [
            FileManagerMock.ProjectFileMock(
                path="open/dontreadme.md", raw_data=BAD_README_RAW_DATA),
        ],
        FILE_COMMITS_SHA["new_bad_dontreadme"]: [
            FileManagerMock.ProjectFileMock(
                path="open/dontreadme.md", raw_data=BAD_README_RAW_DATA_2),
        ],
        FILE_COMMITS_SHA["no_open_source_files"]: [
            FileManagerMock.ProjectFileMock(
                path="dontreadme.md", raw_data=BAD_README_RAW_DATA),
        ],
        FILE_COMMITS_SHA["excluded_open_source_files"]: [
            FileManagerMock.ProjectFileMock(
                path="open/readme.md", raw_data=BAD_README_RAW_DATA),
            FileManagerMock.ProjectFileMock(
                path="open/licenses/some_file.md", raw_data=BAD_README_RAW_DATA),
            FileManagerMock.ProjectFileMock(
                path="open/artifacts/nx_kit/src/json11/a/b/c.c", raw_data=BAD_README_RAW_DATA),
        ],
    })

    @dataclass
    class ProjectFileMock():
        path: str = "foobar"
        ref: str = "11"
        raw_data: str = b"Some data"

        def decode(self):
            return self.raw_data.encode('utf-8')

        @property
        def content(self):
            return base64.b64encode(self.raw_data)

    def get(self, file_path, ref):
        commit_files = self.commit_files[str(ref)]
        file_mock = [f for f in commit_files if f.path == file_path][0]
        file_mock.ref = ref
        return file_mock
