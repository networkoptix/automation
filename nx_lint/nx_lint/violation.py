from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class Violation:
    file_path: Path
    line: Optional[int]
    column: Optional[int]
    offset: Optional[int]
    message: str
    lint_id: str

    def __hash__(self) -> int:
        return hash((
                self.file_path,
                self.line,
                self.column,
                self.offset,
                self.message,
                self.lint_id))

    def to_str(self, relative: bool) -> str:
        if relative:
            file_path = str(self.file_path.absolute().relative_to(Path.cwd()))
        else:
            file_path = str(self.file_path.absolute())

        if self.line:
            if self.column is not None:
                return f"Error: [{self.lint_id}] {file_path}:{self.line}:{self.column}: " \
                       f"{self.message}"
            else:
                return f"Error: [{self.lint_id}] {file_path}:{self.line}: {self.message}"
        else:
            return f"Error: [{self.lint_id}] {file_path}: {self.message}"
