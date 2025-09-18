# nx_lint

// Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

## Introduction

nx_lint is a tool for checking certain aspects of the coding style of the source code to comply
with the Nx rules. It does not attempt to check all rules and recommendations, but rather focuses
on mostly low-level rules which can be checked unambiguously. It is able to automatically fix some
violations when run with the respective command-line argument.

This tool is executed in build pipelines, but you can also run it locally. It supports integration
with Git pre-commit hooks and VSCode. This document will guide you on how to set up and use nx_lint
in various environments.

For a complete list of options and further information on how to use nx_lint, run: `nx_lint --help`

## Installation

### Prerequisites

  * Python 3.12 or newer

For local usage, the recommended way to install nx_lint is via pip:

```sh
pip install ./automation/open/nx_lint #< The exact path depends on your environment.
```

## Configuration

Configuration for nx_lint is contained in a file named `nx_lint.json` in the root of the
repository. Consider the following example (which is a simplified and slightly modified version of
the configuration used in the nx repository):

```json
{
    "include": [
        "**"
    ],
    "exclude": [
        "/.git/**",
        "/open/artifacts/**",
        "/artifacts/**",
        "translations/**/*.ts",
        "translations/**/*.wxl",
        "localization/**/*.wxl"
    ],
    "enabled_rules": [
        "final_newline",
        "trailing_whitespace",
        "filename",
        "empty_lines",
        "control_chars",
        "unix_newlines",
        "tab_chars"
    ],
    "enabled_rules_for_files": {
        "successive_empty_lines": [
            "*.cpp",
            "*.h",
            "*.java",
            "*.md",
            "*.txt"
        ]
    },
    "disabled_rules_for_files": {
        "tab_chars": [
            "*.go", "*.xml", "*.html"
        ]
    }
}
```

The configuration file is a JSON file with the following fields:
    - `include` - A list of glob patterns specifying which files to include in the linting process.
    - `exclude` - An optional list of glob patterns specifying which files to exclude after they
        were included by the `include` field.
    - `enabled_rules` - An optional list of rules which are enabled for all files unless disabled
        via `disabled_rules_for_files`. If this field is not specified, all rules are enabled.
    - `enabled_rules_for_files` - An optional map of rules to file glob patterns for which the rule
        should be enabled in addition to the rules from `enabled_rules`.
    - `disabled_rules_for_files` - An optional map of rules to file glob patterns for which the
        rule should be disabled despite being listed in `enabled_rules` or
        `enabled_rules_for_files`.

Glob patterns work similarly to git:
    - Patterns match anywhere in the repository, unless they start with `/` in which case they
        match only in the root directory.
    - `*` matches any number of characters except `/`, but not recursively.
    - `**` matches any number of characters, including `/`, recursively.

### Order of evaluation

The above fields are evaluated in the following order:
    - `include`
    - `exclude`
    - `enabled_rules`
    - `enabled_rules_for_files`
    - `disabled_rules_for_files`

To learn the identifiers of the rules, run `nx_lint --help`.

## Setting Up Git pre-commit Hook

You can easily set up a Git pre-commit hook to automatically lint your staged files when you
attempt to make a commit. To do this, paste the following code into a file named `pre-commit` in
your `.git/hooks/` directory:

```bash
#!/bin/bash

staged_files=$(git diff --cached --name-only)

for f in ${staged_files}; do
    exec nx_lint --file "${f}"
done
```

Make sure to give execute permission to the `pre-commit` script:

```bash
chmod +x .git/hooks/pre-commit
```

### Fixing violations via Git commit hook

Certain issues, such as trailing whitespace, are automatically fixable by `nx_lint`. You can do
this even in the git commit hook. When an issue is encountered, nx_lint will prevent committing
the file, but it will also fix it in place. You will then need to stage the new changes to be
able to commit. To enable automatic fixing, add the following argument to `nx_lint`: `--fix ALL`

NOTE: Instead of the special value `ALL`, you can name individual rules - see their list in the
command-line help. `--fix` can be specified multiple times.

## Integration with VSCode

To integrate nx_lint with VSCode, you can set up a task in your `tasks.json` file to run the
linting command. Below is an example configuration that you can include in your `tasks.json`:

```json
{
   "label": "Run nx_lint",
   "type": "shell",
   "command": "${command:python.interpreterPath}",
   "presentation": {
      "reveal": "never",
      "panel": "shared"
   },
   "args": [
      "-m",
      "nx_lint.cli",
      "--file",
      "${file}"
   ],
   "problemMatcher": {
      "owner": "Python",
      "pattern": {
         "regexp": "^Error: \\[([^\\]]+)\\] (\\S+):(\\d+):(\\d+): (.*)$",
         "file": 2,
         "line": 3,
         "column": 4,
         "message": 5
      }
   }
}
```

Once this is set up, you can execute the linting task through the VSCode task runner.
