## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
import re


def get_trademarks_from_file(file: Path, common_words: list[str]) -> set[str]:
    exceptions = ['new', 'megapixel', 'nfs', 'axis']
    trademarks = set()
    for line in file.read_text().splitlines():
        no_email_str, _ = line.split(' [')
        *_, raw_org_name = no_email_str.split('_deleted_')
        for trademark in raw_org_name.split(' / '):
            if trademark.lower() not in common_words:
                trademarks.add(trademark)
    return trademarks


def make_trademarks_re(config_directory: Path) -> re.Pattern:
    common_words = (config_directory / 'trademark_common_words.txt').read_text().splitlines()
    special_cases_pattern = '|'.join(
        (config_directory / 'trademark_special_case_patterns.txt').read_text().splitlines())
    boundary_pattern = r'(\b|_|-)'  # For cases where _is_a_morpheme() fails
    trademarks = []
    for trademark in get_trademarks_from_file(
            file=config_directory / 'organization_domains.txt', common_words=common_words):
        escaped_trademark = re.escape(trademark)
        prepared_trademark = escaped_trademark
        # Short abbreviations might easily be a part of a word.
        if len(escaped_trademark) <= 3:
            prepared_trademark = rf'{boundary_pattern}{trademark}{boundary_pattern}'
        if re.search(special_cases_pattern, trademark, flags=re.IGNORECASE):
            continue
        trademarks.append(prepared_trademark)
    result_pattern = f'{special_cases_pattern}|{"|".join(trademarks)}'
    return re.compile(result_pattern, flags=re.IGNORECASE)
