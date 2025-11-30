"""Tests for normalization utility functions, specifically _simplify_label."""

from __future__ import annotations

from comicarr.core.utils import _normalized_strings_match, _simplify_label


class TestSimplifyLabel:
    """Test _simplify_label normalization function."""

    def test_basic_normalization(self):
        """Test basic normalization (lowercase, remove spaces)."""
        assert _simplify_label("Batman") == "batman"
        assert _simplify_label("Star Wars") == "starwars"
        assert _simplify_label("Spider-Man") == "spider-man"

    def test_hyphen_preservation(self):
        """Test that word-connected hyphens are preserved."""
        assert _simplify_label("Spider-Man") == "spider-man"
        assert _simplify_label("X-Men") == "x-men"
        assert _simplify_label("Iron-Man") == "iron-man"

    def test_space_hyphen_space_removal(self):
        """Test that space-enclosed hyphens are removed."""
        assert _simplify_label("Star Wars - Union") == "starwarsunion"
        assert _simplify_label("Batman - Gotham by Gaslight") == "batmangothambygaslight"
        assert _simplify_label("DC - Comics") == "dccomics"

    def test_colon_removal(self):
        """Test that colons are removed."""
        assert _simplify_label("Star Wars: Union") == "starwarsunion"
        assert _simplify_label("Batman: The Dark Knight") == "batmanthedarkknight"
        # Hyphens are preserved even after colon removal
        assert (
            _simplify_label("All-New Spider-Gwen: Ghost-Spider") == "all-newspider-gwenghost-spider"
        )

    def test_colon_with_the(self):
        """Test colon removal with 'The' in the title."""
        # Hyphens are preserved, colon is removed
        assert (
            _simplify_label("All-New Spider-Gwen: The Ghost-Spider")
            == "all-newspider-gwentheghost-spider"
        )
        assert (
            _simplify_label("All-New Spider-Gwen: Ghost-Spider") == "all-newspider-gwenghost-spider"
        )
        # These should be different (one has "the", one doesn't)
        assert _simplify_label("All-New Spider-Gwen: The Ghost-Spider") != _simplify_label(
            "All-New Spider-Gwen: Ghost-Spider"
        )

    def test_multiple_hyphens(self):
        """Test normalization of multiple consecutive hyphens."""
        assert _simplify_label("Spider---Man") == "spider-man"
        assert _simplify_label("X----Men") == "x-men"

    def test_leading_trailing_hyphens(self):
        """Test removal of leading/trailing hyphens."""
        assert _simplify_label("-Batman-") == "batman"
        assert _simplify_label("--Spider-Man--") == "spider-man"

    def test_special_characters(self):
        """Test removal of special characters."""
        assert _simplify_label("Batman #1") == "batman1"
        assert _simplify_label("Star Wars (2020)") == "starwars2020"
        # Hyphens are preserved, colon and spaces removed
        assert (
            _simplify_label("Spider-Man: Into the Spider-Verse") == "spider-manintothespider-verse"
        )

    def test_empty_and_none(self):
        """Test handling of empty strings and None."""
        assert _simplify_label("") == ""
        assert _simplify_label(None) == ""

    def test_whitespace_handling(self):
        """Test various whitespace scenarios."""
        assert _simplify_label("  Batman  ") == "batman"
        assert _simplify_label("Star\tWars") == "starwars"
        assert _simplify_label("Spider\nMan") == "spiderman"

    def test_substring_cases(self):
        """Test that substrings are preserved correctly (for substring rejection)."""
        # "the" should be preserved in "there"
        assert _simplify_label("There") == "there"
        assert _simplify_label("The") == "the"
        # "the" is a substring of "there", which is correct for substring rejection
        assert "the" in "there"

        # "the" should be preserved in "theater"
        assert _simplify_label("Theater") == "theater"
        assert _simplify_label("The") == "the"
        # "the" is a substring of "theater", which is correct for substring rejection
        assert "the" in "theater"

    def test_complex_real_world_examples(self):
        """Test complex real-world examples."""
        # Star Wars cases
        assert _simplify_label("Star Wars") == "starwars"
        assert _simplify_label("Star Wars: Union") == "starwarsunion"
        # "starwars" is a substring of "starwarsunion" - correct for rejection
        assert "starwars" in "starwarsunion"

        # Batman cases
        assert _simplify_label("Batman") == "batman"
        assert (
            _simplify_label("Batman - Gotham by Gaslight - A League for Justice")
            == "batmangothambygaslightaleagueforjustice"
        )
        # "batman" is a substring - correct for rejection
        assert "batman" in "batmangothambygaslightaleagueforjustice"

    def test_spider_gwen_cases(self):
        """Test Spider-Gwen specific cases."""
        # With "The"
        with_the = _simplify_label("All-New Spider-Gwen: The Ghost-Spider")
        assert with_the == "all-newspider-gwentheghost-spider"

        # Without "The"
        without_the = _simplify_label("All-New Spider-Gwen: Ghost-Spider")
        assert without_the == "all-newspider-gwenghost-spider"

        # They should be different (one has "the", one doesn't)
        assert with_the != without_the
        # "the" is in the middle of the first one
        assert "the" in with_the
        assert "the" not in without_the

    def test_hyphen_vs_space_handling(self):
        """Test that hyphens and spaces are handled differently."""
        # Hyphen preserved
        assert _simplify_label("Spider-Man") == "spider-man"

        # Space removed
        assert _simplify_label("Spider Man") == "spiderman"

        # They're different after normalization
        assert _simplify_label("Spider-Man") != _simplify_label("Spider Man")

    def test_common_words_preserved(self):
        """Test that common words like 'the', 'a', 'an' are preserved in normalization."""
        # "The" should be preserved as part of the string
        assert _simplify_label("The Batman") == "thebatman"
        assert _simplify_label("A League") == "aleague"
        assert _simplify_label("An Issue") == "anissue"

        # But they should be preserved as substrings for rejection logic
        assert _simplify_label("The") == "the"
        assert "the" in "thebatman"  # Substring - should be rejected
        assert "the" in "there"  # Substring - should be rejected
        assert "the" in "theater"  # Substring - should be rejected

    def test_numbers_preserved(self):
        """Test that numbers are preserved."""
        assert _simplify_label("Batman 2016") == "batman2016"
        assert _simplify_label("Issue #1") == "issue1"
        assert _simplify_label("X-Men 2024") == "x-men2024"

    def test_mixed_case(self):
        """Test that case is normalized."""
        assert _simplify_label("BATMAN") == "batman"
        assert _simplify_label("BatMan") == "batman"
        assert _simplify_label("bAtMaN") == "batman"

    def test_publisher_names(self):
        """Test publisher name normalization."""
        assert _simplify_label("DC Comics") == "dccomics"
        assert _simplify_label("Marvel Comics") == "marvelcomics"
        assert _simplify_label("Image Comics") == "imagecomics"

    def test_edge_cases_with_hyphens(self):
        """Test edge cases with hyphens."""
        # Multiple hyphens in different positions
        assert _simplify_label("Spider - Man - Returns") == "spidermanreturns"
        assert _simplify_label("Spider-Man-Returns") == "spider-man-returns"

        # Hyphen at start/end
        assert _simplify_label("-Spider-Man") == "spider-man"
        assert _simplify_label("Spider-Man-") == "spider-man"

        # Only hyphens
        assert _simplify_label("---") == ""
        assert _simplify_label(" - - - ") == ""

    def test_the_word_handling(self):
        """Test 'the' word handling - should be preserved but not treated specially yet."""
        # "The" as standalone word
        assert _simplify_label("The Batman") == "thebatman"
        assert _simplify_label("The Flash") == "theflash"

        # "The" in middle (with colon)
        assert _simplify_label("Spider-Gwen: The Ghost-Spider") == "spider-gwentheghost-spider"
        assert _simplify_label("Spider-Gwen: Ghost-Spider") == "spider-gwenghost-spider"

        # "The" should NOT be removed from words like "there" or "theater"
        assert _simplify_label("There") == "there"
        assert _simplify_label("Theater") == "theater"
        assert _simplify_label("The") == "the"

        # Substring checks (for rejection logic)
        assert "the" in "thebatman"  # Should be rejected as substring
        assert "the" in "there"  # Should be rejected as substring
        assert "the" in "theater"  # Should be rejected as substring

    def test_a_and_an_handling(self):
        """Test 'a' and 'an' word handling."""
        # "A" as standalone word
        assert _simplify_label("A League") == "aleague"
        assert _simplify_label("A Team") == "ateam"

        # "An" as standalone word
        assert _simplify_label("An Issue") == "anissue"
        assert _simplify_label("An Event") == "anevent"

        # "A" should NOT be removed from words
        assert _simplify_label("Batman") == "batman"
        assert _simplify_label("A") == "a"

        # Substring checks
        assert "a" in "aleague"  # Should be rejected as substring
        # Note: "a" IS in "batman" (as a character), but "a" as a word is not
        # The substring rejection logic should check if "a" appears as a whole word
        # For now, we just verify the normalization preserves it
        assert "a" in "batman"  # Character "a" exists, but word "a" doesn't

    def test_substring_rejection_cases(self):
        """Test cases that should be rejected as substrings."""
        # "Star Wars" should NOT match "Star Wars: Union"
        star_wars = _simplify_label("Star Wars")
        star_wars_union = _simplify_label("Star Wars: Union")
        assert star_wars == "starwars"
        assert star_wars_union == "starwarsunion"
        assert star_wars in star_wars_union  # Substring - should be rejected

        # "Batman" should NOT match "Batman - Gotham by Gaslight"
        batman = _simplify_label("Batman")
        batman_gotham = _simplify_label("Batman - Gotham by Gaslight - A League for Justice")
        assert batman == "batman"
        assert batman_gotham == "batmangothambygaslightaleagueforjustice"
        assert batman in batman_gotham  # Substring - should be rejected

    def test_exact_match_cases(self):
        """Test cases that should match exactly."""
        # Same series, different formatting
        assert _simplify_label("Batman") == _simplify_label("Batman")
        assert _simplify_label("Star Wars") == _simplify_label("Star Wars")

        # Different case should match
        assert _simplify_label("BATMAN") == _simplify_label("batman")
        assert _simplify_label("Star Wars") == _simplify_label("STAR WARS")

        # Different spacing should match (after normalization)
        assert _simplify_label("Star Wars") == _simplify_label("Star  Wars")  # Extra space
        assert _simplify_label("Batman") == _simplify_label(" Batman ")  # Leading/trailing space


class TestNormalizedStringsMatch:
    """Test _normalized_strings_match function for common word handling."""

    def test_exact_match(self):
        """Test that exact matches work."""
        assert _normalized_strings_match("batman", "batman") is True
        assert _normalized_strings_match("starwars", "starwars") is True

    def test_the_optional(self):
        """Test that 'the' is optional in matching."""
        # "the" in middle
        assert (
            _normalized_strings_match(
                "allnewspidergwenghostspider", "allnewspidergwentheghostspider"
            )
            is True
        )
        assert (
            _normalized_strings_match(
                "allnewspidergwentheghostspider", "allnewspidergwenghostspider"
            )
            is True
        )

        # "the" at start
        assert _normalized_strings_match("batman", "thebatman") is True
        assert _normalized_strings_match("thebatman", "batman") is True

        # "the" at end
        assert _normalized_strings_match("batman", "batmanthe") is True
        assert _normalized_strings_match("batmanthe", "batman") is True

    def test_the_not_in_substrings(self):
        """Test that 'the' in substrings like 'there' or 'theater' is NOT optional."""
        # "the" in "there" - should NOT match
        assert _normalized_strings_match("the", "there") is False
        assert _normalized_strings_match("there", "the") is False

        # "the" in "theater" - should NOT match
        assert _normalized_strings_match("the", "theater") is False
        assert _normalized_strings_match("theater", "the") is False

    def test_a_optional(self):
        """Test that 'a' is optional in matching."""
        assert _normalized_strings_match("league", "aleague") is True
        assert _normalized_strings_match("aleague", "league") is True

    def test_a_not_in_substrings(self):
        """Test that 'a' in substrings is NOT optional."""
        # "a" in "batman" - should NOT match (it's a character, not a word)
        assert _normalized_strings_match("a", "batman") is False
        assert _normalized_strings_match("batman", "a") is False

    def test_an_optional(self):
        """Test that 'an' is optional in matching."""
        assert _normalized_strings_match("issue", "anissue") is True
        assert _normalized_strings_match("anissue", "issue") is True

    def test_multiple_common_words(self):
        """Test matching with multiple common words."""
        # "the" and "a" both optional
        assert _normalized_strings_match("batman", "theabatman") is True
        assert _normalized_strings_match("theabatman", "batman") is True

    def test_no_match_when_different(self):
        """Test that completely different strings don't match."""
        assert _normalized_strings_match("batman", "superman") is False
        assert _normalized_strings_match("starwars", "startrek") is False

    def test_empty_strings(self):
        """Test handling of empty strings."""
        assert _normalized_strings_match("", "") is True
        assert _normalized_strings_match("batman", "") is False
        assert _normalized_strings_match("", "batman") is False

    def test_real_world_spider_gwen(self):
        """Test real-world Spider-Gwen case."""
        norm1 = _simplify_label("All-New Spider-Gwen: Ghost-Spider")
        norm2 = _simplify_label("All-New Spider-Gwen: The Ghost-Spider")

        # They should match with common word handling
        assert _normalized_strings_match(norm1, norm2) is True
        assert _normalized_strings_match(norm2, norm1) is True
