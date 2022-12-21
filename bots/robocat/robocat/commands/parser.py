from typing import List

from robocat.commands.commands import (
    BaseCommand,
    ProcessCommand,
    RunPipelineCommand,
    FollowUpCommand,
    DraftFollowUpCommand)


def command_classes() -> List[BaseCommand]:
    return [ProcessCommand, RunPipelineCommand, FollowUpCommand, DraftFollowUpCommand]


def create_command_from_text(username: str, text: str) -> BaseCommand:
    tokens = text.partition('\n')[0].split()
    if len(tokens) < 2 or tokens[0] != f'@{username}':
        return None
    return next((cls() for cls in command_classes() if tokens[1] in cls.verb_aliases), None)
