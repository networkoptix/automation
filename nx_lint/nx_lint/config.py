## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path


def process_pattern(pattern: str) -> str:
    """
    Implicitly add **/ in front of the pattern, unless the pattern starts with "**" or '/'
    This makes the behavior of glob patterns more intuitive (closer to how .gitignore works).
    """
    if pattern.startswith("**/"):
        return pattern
    elif pattern.startswith("/"):
        return pattern[1:]
    return f"**/{pattern}"


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

    # A dictionary where the keys are rule names and the values are lists of file patterns that
    # should be included in that rule. The lists of include patterns and exclude patterns are
    # considered before the rule inclusions.
    rule_inclusions: dict[str, list[str]]

    # A dictionary where the keys are rule names and the values are lists of file patterns that
    # should be excluded from that rule. The lists of include patterns, exclude patterns and
    # rule inclusions are considered before the rule exclusions.
    rule_exclusions: dict[str, list[str]]

    @classmethod
    def load(cls, repo_root: Path, args: Namespace, file_name: str = "nx_lint.json") -> "Config":
        import json

        try:
            with (repo_root / file_name).open("r") as fp:
                config = json.load(fp)
                include = config.get("include", ["**"])
                exclude = config.get("exclude", [])
                enabled_rules = args.enabled_rules or config.get("enabled_rules", [])
                rule_inclusions = config.get("rule_inclusions", {})
                rule_exclusions = config.get("rule_exclusions", {})

                include = [process_pattern(p) for p in include]
                exclude = [process_pattern(p) for p in exclude]
                for rule, patterns in rule_inclusions.items():
                    rule_inclusions[rule] = [process_pattern(p) for p in patterns]
                for rule, patterns in rule_exclusions.items():
                    rule_exclusions[rule] = [process_pattern(p) for p in patterns]

                return cls(
                    include=include,
                    exclude=exclude,
                    enabled_rules=enabled_rules,
                    rule_inclusions=rule_inclusions,
                    rule_exclusions=rule_exclusions)

        except FileNotFoundError:
            return cls(
                include=["**"],
                exclude=[],
                enabled_rules=[],
                rule_inclusions={},
                rule_exclusions={})

    def rule_enabled(self, rule_name: str) -> bool:
        if not self.enabled_rules:
            return True
        return rule_name in self.enabled_rules
