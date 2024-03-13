## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
from typing import Optional

from nx_lint.config import Config
from nx_lint.violation import Violation
from nx_lint.rules import Rule


class Linter:
    def __init__(self, config: Config, create_backups: bool):
        from nx_lint.rules import RULES
        from nx_lint.file_cache import FileCache

        self.rule_classes = RULES
        self.all_rules = {rule.identifier: rule() for rule in self.rule_classes}

        # Rules that apply to all files.
        global_rules: dict[str, Rule] = {
            rule.identifier: rule
            for rule in self.all_rules.values()
            if rule.identifier in config.enabled_rules
        }
        self.pattern_enabled_rules = {"**/*": list(global_rules.keys())}
        for rule_id, patterns in config.rule_inclusions.items():
            for pattern in patterns:
                if pattern not in self.pattern_enabled_rules:
                    self.pattern_enabled_rules[pattern] = []
                self.pattern_enabled_rules[pattern].append(rule_id)

        self.pattern_disabled_rules = {}
        for rule_id, patterns in config.rule_exclusions.items():
            for pattern in patterns:
                if pattern not in self.pattern_disabled_rules:
                    self.pattern_disabled_rules[pattern] = []
                self.pattern_disabled_rules[pattern].append(rule_id)

        self.config = config
        self.create_backups = create_backups
        self.cache = FileCache()
        self.fixed_files = set()
        self.backup_files = set()

    def _rules_for_file(self, file_path: Path) -> list[Rule]:
        from globmatch import glob_match

        rules = set()
        # First, consider all the enabled rules (global and per-pattern enabled rules are already
        # collected in self.pattern_enabled_rules):
        for pattern, rule_ids in self.pattern_enabled_rules.items():
            if glob_match(file_path, [pattern]):
                rules.update(rule_ids)
        # Then, remove all the per-pattern disabled rules:
        for pattern, rule_ids in self.pattern_disabled_rules.items():
            if glob_match(file_path, [pattern]):
                rules.difference_update(rule_ids)

        return [self.all_rules[rule_id] for rule_id in rules]

    def lint(self, file_path: Path) -> list[Violation]:
        from itertools import chain

        results = chain.from_iterable(
            rule.check_file(file_path, self.cache)
            for rule in self._rules_for_file(file_path))
        return list(results)

    def print_stats(self, results: list[list[Violation]], untracked: Optional[list[str]]) -> None:
        from collections import Counter
        from itertools import chain

        lint_ids = (result.lint_id for result in chain.from_iterable(results))
        lint_id_counts = Counter(lint_ids)
        if any(count for count in lint_id_counts.values()):
            print("\nRule violations:")
            for lint_id, count in lint_id_counts.items():
                print(f"  {lint_id}: {count}")
        else:
            print("No violations found.")

        if untracked:
            print("\nThe following files were not checked because they are not tracked or staged "
                  "in git:")
            for file_path in untracked:
                print(f"  {file_path}")
            print("\nTo check these files, either stage or commit them, or pass "
                  "-u/--include-untracked.")

        if self.fixed_files:
            print("\nFixed files:")
            for file_path in self.fixed_files:
                print(f"  {file_path}")

        if self.backup_files:
            print("\nBackup files were created due to untracked changes:")
            for file_path in self.backup_files:
                print(f"  {file_path}")

            print("\nTo disable backup creation, pass -nb or --no-backup.")

    def create_backup_if_needed(self, file_path: Path):
        if not self.create_backups:
            return

        import re
        import shutil

        from nx_lint.utils import is_tracked, is_different_from_git_head

        if not is_tracked(file_path) or is_different_from_git_head(file_path):
            all_backups = list(sorted(file_path.parent.rglob(f"{file_path.name}.*.bak")))
            bak_num = 0
            if all_backups:
                if match := re.search(r"\.(\d+)\.bak$", all_backups[-1].name):
                    bak_num = int(match.group(1)) + 1
            backup_file_path = file_path.parent / f"{file_path.name}.{bak_num}.bak"
            shutil.copy(file_path, backup_file_path)
            self.backup_files.add(backup_file_path)

    def fix(self, file_path: Path, rule_id: str):
        rule = self.all_rules[rule_id]
        if rule.can_fix(file_path):
            self.create_backup_if_needed(file_path)
            rule.fix_file(file_path, self.cache)
            self.fixed_files.add(file_path)


def lint_files(args) -> int:
    """ Lints the given files or the entire repo if no files are given. Returns the number of
        violations. """
    import logging
    from itertools import chain
    from concurrent.futures import ThreadPoolExecutor

    from globmatch import glob_match

    from nx_lint.result_printer import ResultPrinter
    from nx_lint.utils import is_in_nx_submodule

    repo_directory = (Path(args.repo_dir) if args.repo_dir else Path.cwd()).resolve()
    if not repo_directory.is_dir():
        logging.error(f"Repo directory {str(repo_directory)} does not exist.")
        return -1

    untracked = None
    if args.file:
        files = [args.file]
    elif args.check_dir:
        files = (repo_directory / args.check_dir).rglob("*")
    elif args.check_file_list:
        with open(args.check_file_list) as file_list:
            files = (repo_directory / Path(f.rstrip()) for f in file_list.readlines())
    elif not args.include_untracked:
        from nx_lint.utils import git_tracked_files, git_staged_files, git_untracked_files
        tracked_files = git_tracked_files()
        staged_files = git_staged_files()
        untracked = git_untracked_files()
        files = tracked_files.union(staged_files)
    else:
        files = repo_directory.rglob("*")

    files = set(files)
    printer = ResultPrinter(args.output_format, args.display_absolute_paths)
    config = Config.load(repo_directory, args)
    linter = Linter(config, args.create_backups)

    def should_check_file(file_path: Path) -> bool:
        if file_path == args.file:
            return True
        if is_in_nx_submodule(file_path):
            return False
        rel_file_path = (
            file_path.relative_to(repo_directory)
            if file_path.is_absolute()
            else file_path)
        return glob_match(rel_file_path, config.include) and not glob_match(
            rel_file_path, config.exclude)

    def check_one_file(file_path: Path):
        if not file_path.is_file():
            return []
        if should_check_file(file_path):
            results = linter.lint(file_path)
            for result in results:
                printer.print(result)
                if result.lint_id in args.fix_rules or "ALL" in args.fix_rules:
                    linter.fix(file_path, result.lint_id)
            return results
        return []

    results = []
    with ThreadPoolExecutor() as executor:
        results.extend(executor.map(check_one_file, files))

    linter.print_stats(results, untracked)

    if args.csv_file:
        printer.write_csv(args.csv_file, results)

    return len(list(chain.from_iterable(results)))
