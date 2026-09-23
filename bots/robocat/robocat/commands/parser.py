## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/


from robocat.commands.commands import (
    BaseCommand,
    DraftFollowUpCommand,
    FollowUpCommand,
    ProcessCommand,
    RunPipelineCommand,
    UnknownCommand,
)


def command_classes() -> list[type[BaseCommand]]:
    return [ProcessCommand, RunPipelineCommand, FollowUpCommand, DraftFollowUpCommand]


def create_command_from_text(username: str, text: str) -> BaseCommand | None:
    tokens = text.partition('\n')[0].split()
    if len(tokens) < 2 or tokens[0] != f'@{username}':
        return None
    return next(
        (cls(*tokens[1:]) for cls in command_classes() if tokens[1] in cls.verb_aliases),
        UnknownCommand(*tokens[1:]))
