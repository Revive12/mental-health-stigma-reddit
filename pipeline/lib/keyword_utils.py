"""Shared keyword and Reddit id helpers for the mental-health retrieval scripts."""

from __future__ import annotations

import re
from typing import Iterable, Pattern


# CHI 2023 paper Table 1 retrieval keywords. Table A3 is the later
# Approval/Stigma measurement lexicon and should not be mixed into this list.
MENTAL_HEALTH_KEYWORDS: tuple[str, ...] = (
 "anxiety",
 "depression",
 "mental health",
 "mental illness",
 "mental disorder",
 "bipolar",
 "bpd",
 "ptsd",
 "paranoia",
 "schizophrenia",
 "schizophrenic",
 "schizo",
 "panic attack",
 "panic",
 "anxiety attack",
 "social anxiety",
 "self harm",
 "self-harm",
 "eating disorder",
 "binge eating disorder",
 "anorexia",
 "anorexic",
 "bulimia",
 "bulimic",
 "unwanted",
 "stress",
 "depressed",
 "depressing",
 "suicidal",
 "suicide",
)

POST_SEARCH_FIELDS: tuple[str, ...] = ("title", "selftext")
COMMENT_SEARCH_FIELDS: tuple[str, ...] = ("body",)


def normalize_post_id(post_id: object) -> str:
	"""Return a Reddit submission id without the optional t3_ prefix."""
	if post_id is None:
		return ""
	value = str(post_id).strip()
	if value.startswith("t3_"):
		return value[3:]
	return value


def post_id_variants(post_id: object) -> set[str]:
	base_id = normalize_post_id(post_id)
	if not base_id:
		return set()
	return {base_id, f"t3_{base_id}"}


def _keyword_pattern(keyword: str) -> str:
	escaped = re.escape(keyword).replace(r"\ ", r"\s+")
	prefix = r"(?<![A-Za-z0-9])" if keyword[0].isalnum() else ""
	suffix = r"(?![A-Za-z0-9])" if keyword[-1].isalnum() else ""
	return f"{prefix}{escaped}{suffix}"


def compile_keyword_patterns(
 keywords: Iterable[str] = MENTAL_HEALTH_KEYWORDS,
 case_sensitive: bool = False,
) -> list[tuple[str, Pattern[str]]]:
	flags = 0 if case_sensitive else re.IGNORECASE
	return [(keyword, re.compile(_keyword_pattern(keyword), flags)) for keyword in keywords]


def matched_keywords_in_text(
 text: object,
 patterns: Iterable[tuple[str, Pattern[str]]],
) -> set[str]:
	if not isinstance(text, str) or not text:
		return set()
	return {keyword for keyword, pattern in patterns if pattern.search(text)}


def matched_keywords_in_row(
 row: dict,
 fields: Iterable[str],
 patterns: Iterable[tuple[str, Pattern[str]]],
) -> set[str]:
	matches: set[str] = set()
	for field in fields:
		matches.update(matched_keywords_in_text(row.get(field), patterns))
	return matches


def compile_combined_pattern(
 keywords: Iterable[str] = MENTAL_HEALTH_KEYWORDS,
 case_sensitive: bool = False,
) -> Pattern[str]:
	"""Combine the retrieval keywords into one regular expression."""
	flags = 0 if case_sensitive else re.IGNORECASE
	parts = [_keyword_pattern(keyword) for keyword in keywords]
	return re.compile("(?:" + "|".join(parts) + ")", flags)


def any_keyword_in_row(
 row: dict,
 fields: Iterable[str],
 combined_pattern: Pattern[str],
) -> bool:
	"""Return whether any requested field matches the combined expression."""
	for field in fields:
		text = row.get(field)
		if isinstance(text, str) and text and combined_pattern.search(text):
			return True
	return False
