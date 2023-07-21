class MockFileCache:
    def __init__(self, lines=None, bytes_data=None):
        # latin-1 is not technically correct but it will leave the bytes unchanged, which is what
        # we want.
        self.lines = [line.encode("latin-1") for line in lines] if lines else None
        self.bytes_cache = bytes_data

    def lines_of(self, file_path):
        for num, line in enumerate(self.lines):
            yield num + 1, line

    def bytes_of(self, file_path):
        for byte in self.bytes_cache:
            yield byte

    def cached_contents_of(self, file_path):
        return self.lines
