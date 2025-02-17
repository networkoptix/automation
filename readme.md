# Nx Meta Platform open-source internal automation tools

// Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

This repository contains various tools utilized during the development process by the Nx team.
Below is a brief overview of the repository's contents.

## automation_tools

This directory contains helpers that are used by the other tools in this repository, including
Python `jira` module facades, test mocks, and related support components.

## bots

This directory contains implementations enhancing GitLab functionality. Currently, it features a
single bot named "Robocat". For detailed information about Robocat, refer to the dedicated
documentation in `bots/robocat/readme.md`.

## config_examples

This directory stores example configurations utilized across various tools within the repository.

## nx_lint

A specialized tool designed to enforce specific coding style requirements in source code according
to Nx standards. Detailed specifications can be found in the `nx_lint/readme.md` document.

# nx_source_file_compliance

A Python module responsible for validating source code against company standards. Unlike the
`nx_lint` tool, which focuses on coding style conventions, this module enforces behavioral
guidelines, including restrictions on offensive terminology and trademark usage requirements.
