﻿# -*- coding: utf-8 -*-
# Copyright (C) 2016-2023 PyThaiNLP Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Text normalization
"""
import re
from typing import List, Tuple, Union

from pythainlp import thai_above_vowels as above_v
from pythainlp import thai_below_vowels as below_v
from pythainlp import thai_follow_vowels as follow_v
from pythainlp import thai_lead_vowels as lead_v
from pythainlp import thai_tonemarks as tonemarks
from pythainlp import thai_consonants as consonants
from pythainlp.tokenize import word_tokenize
from pythainlp.corpus import thai_words
from pythainlp.util.trie import Trie

_DANGLING_CHARS = f"{above_v}{below_v}{tonemarks}\u0e3a\u0e4c\u0e4d\u0e4e"
_RE_REMOVE_DANGLINGS = re.compile(f"^[{_DANGLING_CHARS}]+")

_ZERO_WIDTH_CHARS = "\u200b\u200c"  # ZWSP, ZWNJ

# used by remove_repeat_consonants()
# contains all words that has repeating consonants at the end
# for each consonant
# when dictionary updated, this should be updated too
# key: consonant
# value: list of words that has repeating consonants at the end
consonants_repeaters = {}

_REORDER_PAIRS = [
    ("\u0e40\u0e40", "\u0e41"),  # Sara E + Sara E -> Sara Ae
    (
        f"([{tonemarks}\u0e4c]+)([{above_v}{below_v}]+)",
        "\\2\\1",
    ),  # TONE/Thanthakhat + ABV/BLW VOWEL -> ABV/BLW VOWEL + TONE/Thanthakhat
    (
        f"\u0e4d([{tonemarks}]*)\u0e32",
        "\\1\u0e33",
    ),  # Nikhahit + TONEMARK + Sara Aa -> TONEMARK + Sara Am
    (
        f"([{follow_v}]+)([{tonemarks}]+)",
        "\\2\\1",
    ),  # FOLLOW VOWEL + TONEMARK+ -> TONEMARK + FOLLOW VOWEL
    ("([^\u0e24\u0e26])\u0e45", "\\1\u0e32"),  # Lakkhangyao -> Sara Aa
]

# VOWELS + Phinthu, Thanthakhat, Nikhahit, Yamakkan
_NOREPEAT_CHARS = (
    f"{follow_v}{lead_v}{above_v}{below_v}\u0e3a\u0e4c\u0e4d\u0e4e"
)
_NOREPEAT_PAIRS = list(
    zip([f"({ch}[ ]*)+{ch}" for ch in _NOREPEAT_CHARS], _NOREPEAT_CHARS)
)

_RE_TONEMARKS = re.compile(f"[{tonemarks}]+")

_RE_REMOVE_NEWLINES = re.compile("[ \n]*\n[ \n]*")


def _last_char(matchobj):  # to be used with _RE_NOREPEAT_TONEMARKS
    return matchobj.group(0)[-1]


def remove_dangling(text: str) -> str:
    """
    Remove Thai non-base characters at the beginning of text.

    This is a common "typo", especially for input field in a form,
    as these non-base characters can be visually hidden from user
    who may accidentally typed them in.

    A character to be removed should be both:

        * tone mark, above vowel, below vowel, or non-base sign AND
        * located at the beginning of the text

    :param str text: input text
    :return: text without dangling Thai characters at the beginning
    :rtype: str

    :Example:
    ::

        from pythainlp.util import remove_dangling

        remove_dangling('๊ก')
        # output: 'ก'
    """
    return _RE_REMOVE_DANGLINGS.sub("", text)


def remove_dup_spaces(text: str) -> str:
    """
    Remove duplicate spaces. Replace multiple spaces with one space.

    Multiple newline characters and empty lines will be replaced
    with one newline character.

    :param str text: input text
    :return: text without duplicated spaces and newlines
    :rtype: str

    :Example:
    ::

        from pythainlp.util import remove_dup_spaces

        remove_dup_spaces('ก    ข    ค')
        # output: 'ก ข ค'
    """
    while "  " in text:
        text = text.replace("  ", " ")
    text = _RE_REMOVE_NEWLINES.sub("\n", text)
    text = text.strip()
    return text


def remove_tonemark(text: str) -> str:
    """
    Remove all Thai tone marks from the text.

    Thai script has four tone marks indicating four tones as follows:

        * Down tone (Thai: ไม้เอก  _่ )
        * Falling tone  (Thai: ไม้โท  _้ )
        * High tone (Thai: ไม้ตรี  _๊ )
        * Rising tone (Thai: ไม้จัตวา _๋ )

    Putting wrong tone mark is a common mistake in Thai writing.
    By removing tone marks from the string, it could be used to
    for a approximate string matching.

    :param str text: input text
    :return: text without Thai tone marks
    :rtype: str

    :Example:
    ::

        from pythainlp.util import remove_tonemark

        remove_tonemark('สองพันหนึ่งร้อยสี่สิบเจ็ดล้านสี่แสนแปดหมื่นสามพันหกร้อยสี่สิบเจ็ด')
        # output: สองพันหนึงรอยสีสิบเจ็ดลานสีแสนแปดหมืนสามพันหกรอยสีสิบเจ็ด
    """
    for ch in tonemarks:
        while ch in text:
            text = text.replace(ch, "")
    return text


def remove_zw(text: str) -> str:
    """
    Remove zero-width characters.

    These non-visible characters may cause unexpected result from the
    user's point of view. Removing them can make string matching more robust.

    Characters to be removed:

        * Zero-width space (ZWSP)
        * Zero-width non-joiner (ZWJP)

    :param str text: input text
    :return: text without zero-width characters
    :rtype: str
    """
    for ch in _ZERO_WIDTH_CHARS:
        while ch in text:
            text = text.replace(ch, "")

    return text


def reorder_vowels(text: str) -> str:
    """
    Reorder vowels and tone marks to the standard logical order/spelling.

    Characters in input text will be reordered/transformed,
    according to these rules:

        * Sara E + Sara E -> Sara Ae
        * Nikhahit + Sara Aa -> Sara Am
        * tone mark + non-base vowel -> non-base vowel + tone mark
        * follow vowel + tone mark -> tone mark + follow vowel

    :param str text: input text
    :return: text with vowels and tone marks in the standard logical order
    :rtype: str
    """
    for pair in _REORDER_PAIRS:
        text = re.sub(pair[0], pair[1], text)

    return text


def remove_repeat_vowels(text: str) -> str:
    """
    Remove repeating vowels, tone marks, and signs.

    This function will call reorder_vowels() first, to make sure that
    double Sara E will be converted to Sara Ae and not be removed.

    :param str text: input text
    :return: text without repeating Thai vowels, tone marks, and signs
    :rtype: str
    """
    text = reorder_vowels(text)
    for pair in _NOREPEAT_PAIRS:
        text = re.sub(pair[0], pair[1], text)

    # remove repeating tone marks, use last tone mark
    text = _RE_TONEMARKS.sub(_last_char, text)

    return text


def remove_repeat_consonants(
    text: str, dictionary: Trie = None, dictionary_updated: bool = True
) -> str:
    """
    Remove repeating consonants at the last of the sentence.

    This function will remove the repeating consonants
    before a whitespace, new line or at the last
    so that the last word matches a word in the given dictionary.
    If there is no match, the repeating consonants will be
    reduced to one.
    If there are several match, the longest word will be used.
    Since this function uses a dictionary, the result may differs
    depending on the dictionary used.
    Plus, it is recommended to use normalize() to have a better result.

    :param str text: input text
    :param Trie dictionary: Trie dictionary to check the last word.
    If None, pythainlp.corpus.thai_words() will be used
    :param bool dictionary_updated: If the dictionary is updated 
    or the first time using in the kernel, set this true.
    If not, set this false to save time.
    :return: text without repeating Thai consonants
    :rtype: str

    :Example:
    ::

        from pythainlp.util import remove_repeat_consonants
        from pythainlp.util import dict_trie

        # use default dictionary (pythainlp.corpus.thai_words())
        remove_repeat_consonants('เริ่ดดดดดดดด')
        # output: เริ่ด

        remove_repeat_consonants('อืมมมมมมมมมมมมมมม')
        # output: อืมมม
        # "อืมมม" is in the default dictionary

        # use custom dictionary
        custom_dictionary = dict_trie(["อืมมมมม"])
        remove_repeat_consonants('อืมมมมมมมมมมมมมมม', custom_dictionary)
        # output: อืมมมมม

        # long text
        remove_repeat_consonants('อืมมมมมมมมมมมมม คุณมีบุคลิกที่เริ่ดดดดด '\
        'ฉันจะให้เกรดดีกับคุณณณ\nนี่เป็นความลับบบบบ')
        # output: อืมมม คุณมีบุคลิกที่เริ่ด ฉันจะให้เกรดดีกับคุณ
        #         นี่เป็นความลับ
    """
    # use default dictionary if not given
    if dictionary is None:
        dictionary = thai_words()

    # update repeaters dictionary if not updated
    if dictionary_updated:
        _update_consonant_repeaters(dictionary)

    # seperate by newline
    modified_lines = []
    for line in text.split("\n"):
        segments = line.split(" ")

        for cnt, segment in enumerate(segments):
            segments[cnt] = _remove_repeat_consonants_from_segment(
                segment, dictionary
            )

        # revert spaces
        modified_line = " ".join(segments)
        modified_lines.append(modified_line)

    # revert newlines
    modified_text = "\n".join(modified_lines)

    return modified_text


def _remove_repeat_consonants_from_segment(
    segment: str, dictionary: Trie
) -> str:
    """
    Remove repeating consonants at the last of the segment.

    This function process only at the last of the given text.
    Details is same as remove_repeat_consonants().

    :param str segment: segment of text
    :param Trie dictionary: Trie dictionary to check the last word.
    :return: segment without repeating Thai consonants
    :rtype: str
    """
    # skip if the segment is not the target
    if not (
        # the segment is long enough
        (len(segment) > 1)
        # last is Thai consonant
        and (segment[-1] in consonants)
        # has repiitition
        and (segment[-1] == segment[-2])
    ):
        # no need to process
        return segment

    # duplicating character
    dup = segment[-1]

    # find the words that has 2 or more duplication of
    # this character at the end.
    repeaters = consonants_repeaters[dup]

    # remove all of the last repeating character
    segment_head = _get_repitition_head(segment, dup)

    # find the longest word that matches the segment
    longest_word, repetition = _find_longest_consonant_repeaters_match(
        segment_head, repeaters
    )

    if len(longest_word) > 0:
        # if there is a match, use it
        segment = segment_head + (dup * repetition)
    else:
        # if none found,
        # the chance is that the correct is one character,
        # or it's not in the dictionary.

        # make the repition to once
        segment = segment_head + (dup * 1)

    return segment


def _get_repitition_head(text: str, dup: str) -> str:
    """
    Reduce repeating characters at the end of the text.

    This function will remove the repeating characters at the last.
    The text just before the repeating characters will be returned.

    :param str text: input text
    :param str dup: repeating character to be removed
    :return: text without repeating characters at the end
    :rtype: str
    """
    head = text
    while (len(head) > 0) and (head[-1] == dup):
        head = head[:-1]

    return head


def _update_consonant_repeaters(dictionary: Trie) -> None:
    """
    Update dictionary of all words that has
    repeating consonants at the end from the dictionary.

    Search all words in the dictionary that has more than 1 consonants
    repeating at the end and store them in the global dictionary.

    :param str consonant: consonant to be searched
    :param Trie dictionary: Trie dictionary to search
    :rtype: None
    """
    # initialize dictionary
    for consonant in list(consonants):
        consonants_repeaters[consonant] = []

    # register
    for word in dictionary:
        if _is_consonant_repeater(word):
            consonants_repeaters[word[-1]].append(word)

    return


def _is_consonant_repeater(word: str) -> bool:
    """
    Check if the word has repeating consonants at the end.

    This function checks if the word has
    more than 1 repeating consonants at the end.

    :param str word: word to be checked
    :return: True if the word has repeating consonants at the end.
    :rtype: bool
    """
    return (
        (len(word) > 1) and (word[-1] == word[-2]) and (word[-1] in consonants)
    )


def _find_longest_consonant_repeaters_match(
    segment_head: str, repeaters: List[str]
) -> Tuple[str, int]:
    """
    Find the longest word that matches the segment.

    Find the longest word that matches the last
    of the segment from the given repeaters list.
    This returns the word and
    how much the last character is repeated correctly.

    :param str segment: segment of text
    :param List[str] repeaters: list of words
    that has repeating consonants at the end
    :return: "tuple of the word" and
    "how much the last character is repeated correctly"
    If none, ("", 0) will be returned.
    :rtype: Tuple[str, int]
    """
    longest_word = ""  # the longest word that matches the segment
    repetition = 0  # how much the last character is repeated correctly
    for repeater in repeaters:
        # remove all of the last repeating character
        repeater_head = _get_repitition_head(repeater, repeater[-1])

        # check match
        if (
            (len(segment_head) >= len(repeater_head))
            and (segment_head[-len(repeater_head) :] == repeater_head)
            # matched confirmed, check it's longer
            and (len(repeater) > len(longest_word))
        ):
            longest_word = repeater
            repetition = len(repeater) - len(repeater_head)

    return longest_word, repetition


def normalize(text: str) -> str:
    """
    Normalize and clean Thai text with normalizing rules as follows:

        * Remove zero-width spaces
        * Remove duplicate spaces
        * Reorder tone marks and vowels to standard order/spelling
        * Remove duplicate vowels and signs
        * Remove duplicate tone marks
        * Remove dangling non-base characters at the beginning of text

    normalize() simply call remove_zw(), remove_dup_spaces(),
    remove_repeat_vowels(), and remove_dangling(), in that order.

    If a user wants to customize the selection or the order of rules
    to be applied, they can choose to call those functions by themselves.

    Note: for Unicode normalization, see unicodedata.normalize().

    :param str text: input text
    :return: normalized text according to the rules
    :rtype: str

    :Example:
    ::

        from pythainlp.util import normalize

        normalize('เเปลก')  # starts with two Sara E
        # output: แปลก

        normalize('นานาาา')
        # output: นานา
    """
    text = remove_zw(text)
    text = remove_dup_spaces(text)
    text = remove_repeat_vowels(text)
    text = remove_dangling(text)

    return text


def maiyamok(sent: Union[str, List[str]]) -> List[str]:
    """
    Thai MaiYaMok

    MaiYaMok (ๆ) is the mark of duplicate word in Thai language.
    This function is preprocessing MaiYaMok in Thai sentence.

    :param Union[str, List[str]] sent: input sentence (list or str)
    :return: list of words
    :rtype: List[str]

    :Example:
    ::

        from pythainlp.util import maiyamok

        maiyamok("เด็กๆชอบไปโรงเรียน")
        # output: ['เด็ก', 'เด็ก', 'ชอบ', 'ไป', 'โรงเรียน']

        maiyamok(["ทำไม","คน","ดี"," ","ๆ","ๆ"," ","ถึง","ทำ","ไม่ได้"])
        # output: ['ทำไม', 'คน', 'ดี', 'ดี', 'ดี', ' ', 'ถึง', 'ทำ', 'ไม่ได้']
    """
    if isinstance(sent, str):
        sent = word_tokenize(sent)
    _list_word = []
    i = 0
    for j, text in enumerate(sent):
        if text.isspace() and "ๆ" in sent[j + 1]:
            continue
        if " ๆ" in text:
            text = text.replace(" ๆ", "ๆ")
        if "ๆ" == text:
            text = _list_word[i - 1]
        elif "ๆ" in text:
            text = text.replace("ๆ", "")
            _list_word.append(text)
            i += 1
        _list_word.append(text)
        i += 1
    return _list_word
