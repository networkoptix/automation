## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from argparse import ArgumentParser
from textwrap import TextWrapper

from nx_lint.rules import RULES


class NxLintArgumentParser(ArgumentParser):
    """ Custom argument parser for nx_lint with the ability to display the list of available rules
        and their descriptions (acquired from the __doc__ of each rule class) in the help message.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rule_classes = RULES

    def print_help(self, file=None):
        """ Print the help message to stdout. """
        super().print_help(file=file)
        print("\nAvailable rules:\n", file=file)

        for rule in self._rule_classes:
            if rule.__doc__:
                print(f"    {rule.identifier}:", file=file)
                doc = " ".join(line.strip() for line in rule.__doc__.splitlines())
                wrapper = TextWrapper(initial_indent=8 * " ", subsequent_indent=8 * " ", width=80)
                for line in wrapper.wrap(doc):
                    print(line)
                print(file=file)
