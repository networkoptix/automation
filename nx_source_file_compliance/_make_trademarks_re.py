import re


def get_trademarks_from_file(file_path):
    exceptions = ['new', 'megapixel', 'nfs', 'axis']  # This list is discussed with #ababinov
    trademarks = set()
    for line in file_path.read_text().splitlines():
        no_email_str, _ = line.split(' [')
        *_, raw_org_name = no_email_str.split('_deleted_')
        for trademark in raw_org_name.split(' / '):
            if trademark.lower() not in exceptions:
                trademarks.add(trademark)
    return trademarks


def make_trademarks_re(trademarks_file_path):
    boundary_pattern = r'(\b|_|-)'  # For cases where _is_a_morpheme() fails
    special_cases_pattern = (
        rf'hanwha|network[ _-]?optix|digital[ _-]?watchdog|n?optix|spacex|tesla|'
        rf'acti(?!(vat|vit|ve|on|ng))|{boundary_pattern}ness{boundary_pattern}|(?<!m)iscs|'
        rf'reda(?!ss)')
    trademarks = []
    for trademark in get_trademarks_from_file(trademarks_file_path):
        escaped_trademark = re.escape(trademark)
        prepared_trademark = escaped_trademark
        # Short abbreviations like 'DW' or 'UST' might easily be a part of a word
        if len(escaped_trademark) <= 3:
            prepared_trademark = rf'{boundary_pattern}{trademark}{boundary_pattern}'
        if re.search(special_cases_pattern, trademark, flags=re.IGNORECASE):
            continue
        trademarks.append(prepared_trademark)
    result_pattern = f'{special_cases_pattern}|{"|".join(trademarks)}'
    return re.compile(result_pattern, flags=re.IGNORECASE)
