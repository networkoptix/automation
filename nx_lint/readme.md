# nx_lint

## Introduction

nx_lint is a tool for checking the coding style of your source code against the
codified Network Optix rules. It does not implement all rules and
recommendations, but it does implement the most common ones. In some cases, it
is able to automatically fix the violations as well.

This tool is executed in build pipelines, but you can also run it locally. It
supports integration with Git pre-commit hooks and vscode. This document will
guide you on how to set up and use nx_lint in various environments. Getting Help

For a complete list of options and further information on how to use nx_lint,
you can access the help guide by running:

```sh
$ nx_lint --help
```

## Installation

### Prerequisites

  * Python 3.9 or newer
  * Access to the Network Optix PyPI repository in Artifactory (instructions TBD)

For local usage, the recommended way to install nx_lint is via [`pipx`](https://pypa.github.io/pipx/)
which manages a virtual environment for the package and makes it easy to update it later.

```sh
$ pipx install nx_lint
```

Alternatively, you may install the package straight from the source directory:

```sh
$ pipx install ./automation/nx_lint   # The exact path depends on your environment.
```

Without pipx, you are advised to manuall create a virtual environment for the package and install
it there:

```sh
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install ./automation/nx_lint
```

## Setting Up Git pre-commit Hook

You can easily set up a Git pre-commit hook to automatically lint your staged
files. To do this, paste the following code into a file named pre-commit within
your .git/hooks directory:

```bash
#!/bin/bash

staged_files=$(git diff --cached --name-only)

for f in $staged_files; do
  exec nx_lint -r . --output-format simple --display-relative-paths --file $f
done
```

Make sure to give execute permission to the pre-commit script:

```bash
$ chmod +x .git/hooks/pre-commit
```

Now, every time you stage files and attempt to commit, nx_lint will
automatically check the staged files for coding style issues.

## Setting Up in VS Code

To integrate nx_lint with VS Code, you can set up a task in your tasks.json file
to run the linting command. Below is an example configuration that you can
include in your tasks.json:

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
    "--output-format",
    "simple",
    "--display-relative-paths",
    "--file",
    "${file}"
  ],
  "problemMatcher": {
    "owner": "Python",
    "pattern": {
      "regexp": "^(.*):(\\d+):(\\d+):\\s+(.*)$",
      "file": 1,
      "line": 2,
      "column": 3,
      "message": 4
    }
  }
}
```

Once this is set up, you can execute the linting task through the VSCode task runner.
