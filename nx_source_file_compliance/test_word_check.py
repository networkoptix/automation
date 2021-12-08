import unittest
from pathlib import Path

from ._make_trademarks_re import get_trademarks_from_file
from ._source_file_compliance import _find_offensive_words, _find_trademarks, _find_license_words

_offensive_words_criteria_reference = [
    ("Megafuck", 'positive'),
    ("megafuck", 'positive'),
    ("Shithead", 'positive'),
    ("shithead", 'positive'),
    ("SpalshItem", 'negative'),
    ("BreakthroughUI", 'negative'),
    ("BreakthroughUi", 'negative'),
    ("hui_znet_zachem_eta_peremennaya", 'positive'),
    ("AblyArrangedArray", 'negative'),
    ("// Blya - arrange this array at last!", 'positive'),
    ("// #elric, WTF is this?!", 'positive'),
    ("WorldTankFest", 'negative'),
    ("wowTFTP", 'negative'),
    ("That's hell of a code!", 'positive'),
    ("RhelLib", 'negative'),
    ("// What a mess", 'positive'),
    ("MesSysOpt", 'negative'),
    ("EXPECTED_ERROR_MESSAGE", 'negative'),
    ("// errors with messages concatenated via a space.", 'negative'),
    ("errorMessageParts", 'negative'),
    ("EXPECT_EQ(values(), 'a = hello, b = world');", 'negative'),
    ("EXPECT_EQ(countHello(), api::metrics::Value(1));", 'negative'),
    ("UnixShellConsole", 'negative'),
    ]

_trademarks_criteria_reference = [
    ('javaDecoder("com/networkoptix/nxwitness/media/QnAudioDecoder")', 'negative'),
    ('NetworkoptixJavaDecoder("com/networkoptix/nxwitness/media/QnAudioDecoder")', 'positive'),
    ('com/networkoptix/nxwitness/media/QnAudioDecoder', 'negative'),
    ('com/networkoptix/nxwitness/media/NetworkoptixQnAudioDecoder', 'positive'),
    ('com/networkoptix/nxwitness/media/QnAudioDecoder  // Noptix', 'positive'),
    ('com/networkoptix/nxwitness/media/QnAudioDecoder  com/networkoptix/nxwitness', 'negative'),
    ('Biggest electromobile manufactirer, Tesla, is interested in us,', 'positive'),
    ('NIKOLA TESLA\'S BIGGEST INNOVATION', 'positive'),
    ('Teslacars, US', 'positive'),
    ('Crew Dragon was launched by SpaceX', 'positive'),
    ('spaceX = 1024', 'negative'),
    ('spacex\'s achievements are very impressive', 'positive'),
    ('ui->attributesLabel->addHintLine', 'negative'),
    ('// SOV Security\'s product', 'positive'),
    ('// This is UST requirement', 'positive'),
    ('// We MUST add refactor that ASAP!', 'negative'),
    ('bool MustTest = false;', 'negative'),
    ('// This idea belongs to Rite-Hite', 'positive'),
    ('// We are filtering UDP packets here', 'negative'),
    ('DoneItForActiGuys', 'positive'),
    ('ActivateStuff', 'negative'),
    ('SUPER_ACTI_FEATURE', 'positive'),
    ('Activity', 'negative'),
    ('nx::kit::utils::toString(actionUrl);', 'negative'),  # acti
    ('EventIsActive isActive;', 'negative'),  # Acti
    ('kGenerateStonesSetting', 'negative'),  # nesS
    ('runAsAdministratorWithUAC', 'negative'),  # nAsA
    ('business', 'negative'),  # ness
    ('validness', 'negative'),  # ness
    ('megapixel', 'negative'),
    ('maxMegapixels', 'negative'),
    ('{ "nfs", NetworkPartition },', 'negative'),
    ('void moveCursor(const QPoint &aAxis, const QPoint &bAxis);', 'negative'),
    ('axisLocations << parseLocation(modelInfo.zAxis.bits);', 'negative'),
    ('axis: Drag.YAxis', 'negative'),
    *[
        (trademark, 'positive') for trademark in
        get_trademarks_from_file(Path(__file__).parent / 'organizations_domains.txt')
        ],
    ('NVidia Tegra', 'negative'),
    ('Google Test', 'negative'),
    ('NVidia', 'positive'),
    ('Google Inc.', 'positive'),
    ]

_license_words_criteria_reference = [
    ('gpl', 'positive'),
    ('gPl', 'positive'),
    ('copyright', 'positive'),
    ('CopyRighT', 'positive'),
    ('copyrighted', 'positive'),
    ('fcopyright', 'negative'),
    ('"copyright"', 'negative'),
    ('"Copyright"', 'positive'),
    ('copyright_identification_something', 'negative'),
    ('Copyright_identification_something', 'positive'),
    ('copyright_identification', 'positive'),
    ('//1 - Copyrighted.', 'negative'),
    ('1 - Copyrighted to somebody', 'positive'),
]


class TestFindWords(unittest.TestCase):

    def _check_correctness(self, func, words_reference):
        for [phrase, verdict] in words_reference:
            words = [*func(phrase)]
            with self.subTest(phrase=phrase, verdict=verdict):
                if verdict == 'positive':
                    self.assertTrue(words)
                else:
                    self.assertListEqual(words, [])

    def test_offensive_search(self):
        self._check_correctness(_find_offensive_words, _offensive_words_criteria_reference)

    def test_trademark_search(self):
        self._check_correctness(_find_trademarks, _trademarks_criteria_reference)

    def test_license_words_search(self):
        self._check_correctness(_find_license_words, _license_words_criteria_reference)
