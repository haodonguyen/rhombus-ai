"""Safety checks for regex patterns before Spark applies them.

Spark evaluates patterns with java.util.regex, a backtracking engine with no timeout, so a
single pathological pattern can pin executor cores indefinitely. A pattern is applied
only after passing every check here:

1. Syntax: bounded length, no Python-only constructs, compiles as a regex.
2. Structure: no repeated groups whose contents can be split ambiguously across
   iterations (e.g. `(a+)+`, `(\\w+\\s?)*`, `(a|a)*`), the shapes behind catastrophic
   backtracking, and no pattern that can match empty text.
3. Behaviour: stays fast on adversarial inputs built from the pattern's own characters.

Structure is analysed with Python's regex parser (`re._parser`). It is private but stable
across 3.11+, and Python's syntax is close enough to Java's for this purpose. Spark
compiles the pattern in the JVM before running as a final dialect check.

Known limitation: Python's parser merges single-character alternatives into a character
class (`(\\d|\\w)+` becomes `[\\d\\w]+`), so those overlaps are invisible here even though
Java backtracks on them. The LLM prompt asks for character classes instead, and the
task's soft time limit is the last resort.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations
from re import _constants as sre
from re import _parser as sre_parser

import regex

from processing.errors import InvalidPatternError

MAX_PATTERN_LENGTH = 500
# Repeats with more iterations than this are treated like unbounded ones.
WIDE_REPEAT_THRESHOLD = 10
# Long enough that exponential and cubic patterns time out; quadratic ones (common with
# find semantics, e.g. `\S+@\S+`) finish well within the budget.
PROBE_LENGTH = 1024
PROBE_TIMEOUT_SECONDS = 0.1
MAX_PROBE_CHARACTERS = 6

_JAVA_INCOMPATIBLE = [
    (re.compile(r"\(\?P[<=>]"), "Python-style named groups (?P<name>...) are not supported."),
    (
        re.compile(r"\(\?<(?![=!])"),
        "Named groups are not supported; use a non-capturing group (?:...) instead.",
    ),
    (re.compile(r"\(\?\("), "Conditional groups (?(...)...) are not supported."),
    (re.compile(r"\(\?#"), "Inline comments (?#...) are not supported."),
]

_REPEATS = (sre.MAX_REPEAT, sre.MIN_REPEAT)
_CATEGORIES = {
    sre.CATEGORY_DIGIT: "digit",
    sre.CATEGORY_WORD: "word",
    sre.CATEGORY_SPACE: "space",
}
_CATEGORY_REPRESENTATIVES = {"digit": "1", "word": "a", "space": " "}


def check_syntax(pattern: str) -> None:
    """Cheap checks suitable for request validation: length, dialect and compilation."""
    if not pattern:
        raise InvalidPatternError("The pattern is empty.")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise InvalidPatternError(f"The pattern is longer than {MAX_PATTERN_LENGTH} characters.")
    for detector, message in _JAVA_INCOMPATIBLE:
        if detector.search(pattern):
            raise InvalidPatternError(message)
    try:
        re.compile(pattern)
    except re.error as exc:
        raise InvalidPatternError(f"Invalid regular expression: {exc}") from exc


def validate_pattern(pattern: str) -> str:
    """Run every safety check; return the pattern or raise InvalidPatternError."""
    check_syntax(pattern)
    parsed = list(sre_parser.parse(pattern))

    if _nullable(parsed):
        raise InvalidPatternError(
            "The pattern can match empty text, which would insert the replacement between "
            "every character. Make at least one part of it required."
        )
    risk = _find_backtracking_risk(parsed)
    if risk:
        raise InvalidPatternError(
            f"The pattern risks catastrophic backtracking: it contains {risk}."
        )
    _check_performance(pattern, parsed)
    return pattern


def with_inline_flags(
    pattern: str, *, case_insensitive: bool = False, multiline: bool = False, dotall: bool = False
) -> str:
    """Prefix inline flags understood by both Python and Java, e.g. `(?i)`."""
    flags = "".join(
        letter
        for letter, enabled in (("i", case_insensitive), ("m", multiline), ("s", dotall))
        if enabled
    )
    return f"(?{flags}){pattern}" if flags else pattern


# --- character sets -----------------------------------------------------------------


@dataclass(frozen=True)
class _CharSet:
    """Over-approximation of the characters a regex element can consume."""

    chars: frozenset[str] = frozenset()
    categories: frozenset[str] = frozenset()
    universal: bool = False

    @property
    def empty(self) -> bool:
        return not (self.chars or self.categories or self.universal)

    def union(self, other: "_CharSet") -> "_CharSet":
        return _CharSet(
            self.chars | other.chars,
            self.categories | other.categories,
            self.universal or other.universal,
        )

    def overlaps(self, other: "_CharSet") -> bool:
        if self.empty or other.empty:
            return False
        if self.universal or other.universal:
            return True
        if self.chars & other.chars:
            return True
        if any(_in_category(ch, cat) for cat in self.categories for ch in other.chars):
            return True
        if any(_in_category(ch, cat) for cat in other.categories for ch in self.chars):
            return True
        return any(
            a == b or {a, b} == {"digit", "word"} for a in self.categories for b in other.categories
        )

    def representatives(self) -> list[str]:
        samples = sorted(self.chars)[:MAX_PROBE_CHARACTERS]
        samples += [_CATEGORY_REPRESENTATIVES[cat] for cat in sorted(self.categories)]
        if self.universal:
            samples += ["a", "."]
        return list(dict.fromkeys(samples))[:MAX_PROBE_CHARACTERS]


_UNIVERSAL = _CharSet(universal=True)
_NOTHING = _CharSet()


def _in_category(ch: str, category: str) -> bool:
    if category == "digit":
        return ch.isdigit()
    if category == "word":
        return ch.isalnum() or ch == "_"
    return ch.isspace()


def _class_charset(items: Iterable[tuple]) -> _CharSet:
    chars: set[str] = set()
    categories: set[str] = set()
    for op, av in items:
        if op is sre.NEGATE:
            return _UNIVERSAL
        if op is sre.LITERAL:
            chars.add(chr(av))
        elif op is sre.RANGE:
            low, high = av
            if high - low > 256:
                return _UNIVERSAL
            chars.update(chr(code) for code in range(low, high + 1))
        elif op is sre.CATEGORY and av in _CATEGORIES:
            categories.add(_CATEGORIES[av])
        else:
            return _UNIVERSAL
    return _CharSet(frozenset(chars), frozenset(categories))


# --- structural analysis ------------------------------------------------------------


def _children(op, av) -> list[list[tuple]]:
    """Sub-sequences nested inside an element, in the parser's representation."""
    if op is sre.SUBPATTERN:
        return [list(av[3])]
    if op in _REPEATS or op is sre.POSSESSIVE_REPEAT:
        return [list(av[2])]
    if op is sre.ATOMIC_GROUP:
        return [list(av)]
    if op in (sre.ASSERT, sre.ASSERT_NOT):
        return [list(av[1])]
    if op is sre.BRANCH:
        return [list(branch) for branch in av[1]]
    if op is sre.GROUPREF_EXISTS:
        return [list(part) for part in av[1:] if part is not None]
    return []


def _consumed(items: Sequence[tuple]) -> _CharSet:
    result = _NOTHING
    for op, av in items:
        if op is sre.LITERAL:
            result = result.union(_CharSet(frozenset({chr(av)})))
        elif op is sre.IN:
            result = result.union(_class_charset(av))
        elif op in (sre.ANY, sre.NOT_LITERAL, sre.GROUPREF):
            result = result.union(_UNIVERSAL)
        elif op in (sre.ASSERT, sre.ASSERT_NOT, sre.AT):
            continue
        else:
            for child in _children(op, av):
                result = result.union(_consumed(child))
    return result


def _nullable_element(op, av) -> bool:
    if op in (sre.AT, sre.ASSERT, sre.ASSERT_NOT, sre.GROUPREF_EXISTS):
        return True
    if op in _REPEATS or op is sre.POSSESSIVE_REPEAT:
        return av[0] == 0 or _nullable(list(av[2]))
    if op is sre.BRANCH:
        return any(_nullable(list(branch)) for branch in av[1])
    if op in (sre.SUBPATTERN, sre.ATOMIC_GROUP):
        return _nullable(_children(op, av)[0])
    return False


def _nullable(items: Sequence[tuple]) -> bool:
    return all(_nullable_element(op, av) for op, av in items)


def _first(items: Sequence[tuple]) -> _CharSet:
    """Characters that can start a match of the sequence."""
    result = _NOTHING
    for op, av in items:
        if op is sre.BRANCH:
            for branch in av[1]:
                result = result.union(_first(list(branch)))
        elif op in (sre.AT, sre.ASSERT, sre.ASSERT_NOT):
            pass
        elif _children(op, av) and op is not sre.GROUPREF_EXISTS:
            result = result.union(_first(_children(op, av)[0]))
        else:
            result = result.union(_consumed([(op, av)]))
        if not _nullable_element(op, av):
            break
    return result


def _is_wide(maximum: int) -> bool:
    return maximum == sre.MAXREPEAT or maximum > WIDE_REPEAT_THRESHOLD


def _has_backtracking_repeat(op, av) -> bool:
    if op in _REPEATS and av[1] > 1:
        return True
    if op in (sre.ATOMIC_GROUP, sre.POSSESSIVE_REPEAT):
        return False  # the engine never backtracks into these
    return any(_has_backtracking_repeat(o, a) for child in _children(op, av) for o, a in child)


def _unwrap_group(items: list[tuple]) -> list[tuple]:
    while len(items) == 1 and items[0][0] is sre.SUBPATTERN:
        items = list(items[0][1][3])
    return items


def _find_backtracking_risk(items: Sequence[tuple]) -> str | None:
    for op, av in items:
        if op in (sre.ATOMIC_GROUP, sre.POSSESSIVE_REPEAT):
            continue
        if op in _REPEATS and _is_wide(av[1]):
            risk = _risk_in_repeated_body(_unwrap_group(list(av[2])))
            if risk:
                return risk
        for child in _children(op, av):
            risk = _find_backtracking_risk(child)
            if risk:
                return risk
    return None


def _risk_in_repeated_body(body: list[tuple]) -> str | None:
    if _nullable(body):
        return "a repeated group that can match empty text"

    for index, (op, av) in enumerate(body):
        if op is sre.BRANCH and _branches_overlap(av[1]):
            return "alternatives inside a repeated group that can match the same text"
        if not _has_backtracking_repeat(op, av):
            continue
        inner = _consumed([(op, av)])
        others = body[:index] + body[index + 1 :]
        separated = any(
            not _nullable_element(o, a)
            and not _consumed([(o, a)]).universal
            and not _consumed([(o, a)]).overlaps(inner)
            for o, a in others
        )
        if not separated:
            return "a quantifier nested inside another quantifier without a distinct separator"
    return None


def _branches_overlap(branches: Sequence) -> bool:
    sequences = [list(branch) for branch in branches]
    if any(_nullable(sequence) for sequence in sequences):
        return True
    firsts = [_first(sequence) for sequence in sequences]
    return any(a.overlaps(b) for a, b in combinations(firsts, 2))


# --- behavioural check --------------------------------------------------------------


def _check_performance(pattern: str, parsed: Sequence[tuple]) -> None:
    compiled = regex.compile(pattern)
    for probe in _probe_inputs(parsed):
        try:
            compiled.search(probe, timeout=PROBE_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise InvalidPatternError(
                "The pattern is too slow on long inputs and could stall processing."
            ) from exc


def _probe_inputs(parsed: Sequence[tuple]) -> list[str]:
    """Long runs of the pattern's own characters, ending in a character that won't match."""
    characters = _consumed(parsed).representatives() or ["a"]
    suffix = "\x00"
    probes = [ch * PROBE_LENGTH + suffix for ch in characters]
    probes += [(a + b) * (PROBE_LENGTH // 2) + suffix for a, b in combinations(characters, 2)]
    return probes
