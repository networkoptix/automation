from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    # A list of filename patterns that are included in the linting process. If this list is
    # non-empty, only files that match at least one of the patterns will be linted.
    # The list of include patterns is considered before the list of exclude patterns.
    include: list[str]

    # A list of patterns that are excluded from the linting process. If this list is non-empty,
    # any files that match at least one of the patterns will be excluded from linting.
    # The list of include patterns is considered before the list of exclude patterns.
    exclude: list[str]

    # A list of explicitly enabled rules. If this list is non-empty, only rules that are in this
    # list will be enabled. If this list is empty, all rules will be enabled.
    enabled_rules: list[str]

    @classmethod
    def load(cls, repo_root: Path, args: Namespace, file_name: str = "nx_lint.json") -> "Config":
        import json

        try:
            with (repo_root / file_name).open("r") as fp:
                config = json.load(fp)
                include = config.get("include", ["**"])
                exclude = config.get("exclude", [])
                enabled_rules = args.enabled_rules or config.get("enabled_rules", [])
                return cls(include, exclude, enabled_rules)
        except FileNotFoundError:
            return cls(["**"], [], [])

    def rule_enabled(self, rule_name: str) -> bool:
        if not self.enabled_rules:
            return True
        return rule_name in self.enabled_rules
