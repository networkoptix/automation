from robocat.commands.commands import BaseCommand, ProcessCommand, RunPipelineCommand


def create_command_from_text(username: str, text: str) -> BaseCommand:
    tokens = text.partition('\n')[0].split()
    if len(tokens) < 2 or tokens[0] != f'@{username}':
        return None

    classes = (ProcessCommand, RunPipelineCommand)
    return next((cls() for cls in classes if cls.verb == tokens[1]), None)
