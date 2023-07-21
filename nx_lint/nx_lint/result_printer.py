from enum import Enum
from pathlib import Path

from nx_lint.violation import Violation


class OutputFormat(Enum):
    LOG = "log"
    SIMPLE = "simple"


class ResultPrinter:
    def __init__(self, output_format: str, absolute_paths: bool):
        self.output_format = OutputFormat(output_format)
        self.relative_paths = not absolute_paths

    def print(self, result: Violation):
        if self.output_format == OutputFormat.LOG:
            import logging

            logging.info(result.to_str(self.relative_paths))
        elif self.output_format == OutputFormat.SIMPLE:
            print(result.to_str(self.relative_paths))
        else:
            raise NotImplementedError(
                f"Output format {self.output_format} not implemented.")

    def write_csv(self, csv_file: Path, results: list[list[Violation]]):
        import csv
        from itertools import chain

        with csv_file.open("w") as file:
            writer = csv.writer(file)
            writer.writerow([
                    "file_path",
                    "extension",
                    "line",
                    "column",
                    "offset",
                    "lint_id",
                    "message",
                ])
            for result in chain.from_iterable(results):
                writer.writerow([
                        result.file_path
                        if not self.relative_paths
                        else result.file_path.absolute().relative_to(Path.cwd()),
                        result.file_path.suffix,
                        result.line,
                        result.column,
                        result.offset,
                        result.lint_id,
                        result.message])
