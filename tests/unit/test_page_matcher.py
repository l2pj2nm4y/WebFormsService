"""Unit tests for page matching service.

Tests URL similarity, heading matching, structure comparison,
and page grouping algorithms for schema merging.
"""

import pytest

from src.models.page_identification import PageIdentification
from src.models.schema import FormField, FormSchema, FormSection
from src.services.merging.page_matcher import PageMatcher


class TestURLSimilarity:
    """Tests for URL similarity computation."""

    def test_exact_url_match(self) -> None:
        """Test exact URL match returns 1.0."""
        matcher = PageMatcher()

        url = "https://example.gov/form/application"
        similarity = matcher.compute_url_similarity(url, url)

        assert similarity == 1.0

    def test_same_domain_and_path(self) -> None:
        """Test same domain and path returns 0.9."""
        matcher = PageMatcher()

        url1 = "https://example.gov/form?page=1"
        url2 = "https://example.gov/form?page=2"

        similarity = matcher.compute_url_similarity(url1, url2)

        assert similarity == 0.9

    def test_same_domain_different_path(self) -> None:
        """Test same domain but different path returns 0.5."""
        matcher = PageMatcher()

        url1 = "https://example.gov/form/page1"
        url2 = "https://example.gov/form/page2"

        similarity = matcher.compute_url_similarity(url1, url2)

        assert similarity == 0.5

    def test_different_domains(self) -> None:
        """Test different domains returns 0.0."""
        matcher = PageMatcher()

        url1 = "https://example.gov/form"
        url2 = "https://other.gov/form"

        similarity = matcher.compute_url_similarity(url1, url2)

        assert similarity == 0.0

    def test_missing_url(self) -> None:
        """Test missing URL returns 0.0."""
        matcher = PageMatcher()

        similarity = matcher.compute_url_similarity(None, "https://example.gov")

        assert similarity == 0.0


class TestListSimilarity:
    """Tests for list similarity (Jaccard index)."""

    def test_identical_lists(self) -> None:
        """Test identical lists return 1.0."""
        matcher = PageMatcher()

        list1 = ["heading1", "heading2", "heading3"]
        similarity = matcher.compute_list_similarity(list1, list1)

        assert similarity == 1.0

    def test_partial_overlap(self) -> None:
        """Test partial overlap returns correct Jaccard score."""
        matcher = PageMatcher()

        list1 = ["heading1", "heading2", "heading3"]
        list2 = ["heading2", "heading3", "heading4"]

        # Intersection: {heading2, heading3} = 2
        # Union: {heading1, heading2, heading3, heading4} = 4
        # Jaccard: 2/4 = 0.5
        similarity = matcher.compute_list_similarity(list1, list2)

        assert similarity == 0.5

    def test_no_overlap(self) -> None:
        """Test no overlap returns 0.0."""
        matcher = PageMatcher()

        list1 = ["heading1", "heading2"]
        list2 = ["heading3", "heading4"]

        similarity = matcher.compute_list_similarity(list1, list2)

        assert similarity == 0.0

    def test_empty_lists(self) -> None:
        """Test empty lists return 0.0 (no content to match)."""
        matcher = PageMatcher()

        similarity = matcher.compute_list_similarity([], [])

        assert similarity == 0.0

    def test_missing_list(self) -> None:
        """Test missing list returns 0.0."""
        matcher = PageMatcher()

        similarity = matcher.compute_list_similarity(None, ["heading1"])

        assert similarity == 0.0


class TestHeadingSimilarity:
    """Tests for heading similarity computation."""

    def test_identical_headings(self) -> None:
        """Test identical headings return 1.0."""
        matcher = PageMatcher()

        page1 = PageIdentification(
            url="https://example.gov",
            timestamp=None,
            page_headings=["Application Form", "Personal Info"],
            form_headings=["Section 1", "Section 2"],
        )

        similarity = matcher.compute_heading_similarity(page1, page1)

        assert similarity == 1.0

    def test_partial_heading_overlap(self) -> None:
        """Test partial heading overlap returns weighted score."""
        matcher = PageMatcher()

        page1 = PageIdentification(
            url="https://example.gov",
            timestamp=None,
            page_headings=["Application Form", "Personal Info"],
            form_headings=["Section 1", "Section 2"],
        )

        page2 = PageIdentification(
            url="https://example.gov",
            timestamp=None,
            page_headings=["Application Form", "Contact Info"],  # 50% overlap
            form_headings=["Section 1", "Section 3"],  # 50% overlap
        )

        # page_headings: 1/3 = 0.333, weight 0.6
        # form_headings: 1/3 = 0.333, weight 0.4
        # Total: (0.333 * 0.6) + (0.333 * 0.4) = 0.333
        similarity = matcher.compute_heading_similarity(page1, page2)

        assert 0.32 < similarity < 0.35  # Allow for floating point


class TestStructureSimilarity:
    """Tests for visual structure similarity."""

    def test_identical_structure(self) -> None:
        """Test identical structure returns 1.0."""
        matcher = PageMatcher()

        page1 = PageIdentification(
            url="https://example.gov",
            timestamp=None,
            visual_sections=["Header", "Main Form", "Footer"],
        )

        similarity = matcher.compute_structure_similarity(page1, page1)

        assert similarity == 1.0

    def test_partial_structure_overlap(self) -> None:
        """Test partial structure overlap."""
        matcher = PageMatcher()

        page1 = PageIdentification(
            url="https://example.gov",
            timestamp=None,
            visual_sections=["Header", "Main Form", "Footer"],
        )

        page2 = PageIdentification(
            url="https://example.gov",
            timestamp=None,
            visual_sections=["Header", "Side Panel", "Footer"],
        )

        # Intersection: {Header, Footer} = 2
        # Union: {Header, Main Form, Side Panel, Footer} = 4
        # Jaccard: 2/4 = 0.5
        similarity = matcher.compute_structure_similarity(page1, page2)

        assert similarity == 0.5


class TestNavigationSimilarity:
    """Tests for navigation button similarity."""

    def test_identical_navigation(self) -> None:
        """Test identical navigation returns 1.0."""
        matcher = PageMatcher()

        page1 = PageIdentification(
            url="https://example.gov",
            timestamp=None,
            navigation_buttons=["Previous", "Next", "Save"],
        )

        similarity = matcher.compute_navigation_similarity(page1, page1)

        assert similarity == 1.0

    def test_partial_navigation_overlap(self) -> None:
        """Test partial navigation overlap."""
        matcher = PageMatcher()

        page1 = PageIdentification(
            url="https://example.gov",
            timestamp=None,
            navigation_buttons=["Previous", "Next", "Save"],
        )

        page2 = PageIdentification(
            url="https://example.gov",
            timestamp=None,
            navigation_buttons=["Back", "Next", "Submit"],
        )

        # Intersection: {Next} = 1
        # Union: {Previous, Next, Save, Back, Submit} = 5
        # Jaccard: 1/5 = 0.2
        similarity = matcher.compute_navigation_similarity(page1, page2)

        assert similarity == 0.2


class TestOverallSimilarity:
    """Tests for overall similarity computation."""

    def test_compute_similarity_components(self) -> None:
        """Test that similarity returns both score and components."""
        matcher = PageMatcher()

        page1 = PageIdentification(
            url="https://example.gov/form",
            timestamp=None,
            page_headings=["Application"],
            form_headings=["Section 1"],
            visual_sections=["Header", "Main"],
            navigation_buttons=["Next"],
        )

        page2 = PageIdentification(
            url="https://example.gov/form",
            timestamp=None,
            page_headings=["Application"],
            form_headings=["Section 1"],
            visual_sections=["Header", "Main"],
            navigation_buttons=["Next"],
        )

        score, components = matcher.compute_similarity(page1, page2)

        assert abs(score - 1.0) < 0.01  # Allow floating point tolerance
        assert components["url"] == 1.0
        assert components["headings"] == 1.0
        assert components["structure"] == 1.0
        assert components["navigation"] == 1.0

    def test_weighted_similarity_calculation(self) -> None:
        """Test weighted similarity with different component scores."""
        matcher = PageMatcher(
            url_weight=0.4, heading_weight=0.3, structure_weight=0.2, navigation_weight=0.1
        )

        page1 = PageIdentification(
            url="https://example.gov/form",
            timestamp=None,
            page_headings=["Application"],
            form_headings=["Section 1"],
            visual_sections=["Header"],
            navigation_buttons=["Next"],
        )

        page2 = PageIdentification(
            url="https://example.gov/form",  # URL: 1.0
            timestamp=None,
            page_headings=["Different"],  # Headings: 0.0
            form_headings=["Other"],
            visual_sections=["Header"],  # Structure: 1.0
            navigation_buttons=["Next"],  # Navigation: 1.0
        )

        score, _ = matcher.compute_similarity(page1, page2)

        # Expected: (1.0 * 0.4) + (0.0 * 0.3) + (1.0 * 0.2) + (1.0 * 0.1) = 0.7
        assert abs(score - 0.7) < 0.01


class TestPageMatching:
    """Tests for page matching decisions."""

    def test_are_pages_matching_above_threshold(self) -> None:
        """Test pages match when above threshold."""
        matcher = PageMatcher(similarity_threshold=0.5)  # Lower threshold for sparse data

        schema1 = FormSchema(
            page_identifier="page-1",
            form_name="Application",
            description="Test form",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application Form"],
            ),
        )

        schema2 = FormSchema(
            page_identifier="page-2",
            form_name="Application",
            description="Test form",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application Form"],
            ),
        )

        is_match, similarity, _ = matcher.are_pages_matching(schema1, schema2)

        assert is_match is True
        assert similarity > 0.5

    def test_are_pages_matching_below_threshold(self) -> None:
        """Test pages don't match when below threshold."""
        matcher = PageMatcher(similarity_threshold=0.7)

        schema1 = FormSchema(
            page_identifier="page-1",
            form_name="Application",
            description="Test form",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form1",
                timestamp=None,
                page_headings=["Application Form"],
            ),
        )

        schema2 = FormSchema(
            page_identifier="page-2",
            form_name="Different",
            description="Different form",
            sections=[],
            page_identification=PageIdentification(
                url="https://other.gov/form2",
                timestamp=None,
                page_headings=["Contact Form"],
            ),
        )

        is_match, similarity, _ = matcher.are_pages_matching(schema1, schema2)

        assert is_match is False
        assert similarity < 0.7


class TestSchemaGrouping:
    """Tests for grouping schemas by page."""

    def test_group_identical_pages(self) -> None:
        """Test grouping of identical pages."""
        matcher = PageMatcher(similarity_threshold=0.5)  # Lower threshold for sparse data

        schema1 = FormSchema(
            page_identifier="page-1",
            form_name="Application",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application"],
            ),
        )

        schema2 = FormSchema(
            page_identifier="page-2",
            form_name="Application",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application"],
            ),
        )

        groups = matcher.group_schemas_by_page([schema1, schema2])

        assert len(groups) == 1
        group_schemas = list(groups.values())[0]
        assert len(group_schemas) == 2
        assert schema1 in group_schemas
        assert schema2 in group_schemas

    def test_group_different_pages(self) -> None:
        """Test grouping of different pages."""
        matcher = PageMatcher(similarity_threshold=0.7)

        schema1 = FormSchema(
            page_identifier="page-1",
            form_name="Application",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form1",
                timestamp=None,
                page_headings=["Application"],
            ),
        )

        schema2 = FormSchema(
            page_identifier="page-2",
            form_name="Contact",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://other.gov/form2",
                timestamp=None,
                page_headings=["Contact"],
            ),
        )

        groups = matcher.group_schemas_by_page([schema1, schema2])

        assert len(groups) == 2
        assert "page-1" in groups
        assert "page-2" in groups
        assert len(groups["page-1"]) == 1
        assert len(groups["page-2"]) == 1

    def test_group_mixed_pages(self) -> None:
        """Test grouping with mix of matching and different pages."""
        matcher = PageMatcher(similarity_threshold=0.5)  # Lower threshold for sparse data

        schema1 = FormSchema(
            page_identifier="page-1",
            form_name="Application",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application"],
            ),
        )

        schema2 = FormSchema(
            page_identifier="page-2",
            form_name="Application",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application"],
            ),
        )

        schema3 = FormSchema(
            page_identifier="page-3",
            form_name="Contact",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://other.gov/contact",
                timestamp=None,
                page_headings=["Contact"],
            ),
        )

        groups = matcher.group_schemas_by_page([schema1, schema2, schema3])

        assert len(groups) == 2
        # First group should have schema1 and schema2
        first_group = groups["page-1"]
        assert len(first_group) == 2
        # Second group should have schema3
        second_group = groups["page-3"]
        assert len(second_group) == 1

    def test_group_empty_list(self) -> None:
        """Test grouping empty list returns empty dict."""
        matcher = PageMatcher()

        groups = matcher.group_schemas_by_page([])

        assert groups == {}


class TestMatcherConfiguration:
    """Tests for matcher configuration."""

    def test_invalid_weights_raise_error(self) -> None:
        """Test invalid weights raise ValueError."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            PageMatcher(
                url_weight=0.5, heading_weight=0.3, structure_weight=0.3, navigation_weight=0.1
            )

    def test_valid_custom_weights(self) -> None:
        """Test custom weights are accepted."""
        matcher = PageMatcher(
            url_weight=0.5, heading_weight=0.25, structure_weight=0.15, navigation_weight=0.1
        )

        assert matcher.url_weight == 0.5
        assert matcher.heading_weight == 0.25
        assert matcher.structure_weight == 0.15
        assert matcher.navigation_weight == 0.1

    def test_custom_threshold(self) -> None:
        """Test custom similarity threshold."""
        matcher = PageMatcher(similarity_threshold=0.8)

        assert matcher.similarity_threshold == 0.8


class TestFindAllMatches:
    """Tests for finding all pairwise matches."""

    def test_find_all_matches_three_schemas(self) -> None:
        """Test finding all matches in a set of schemas."""
        matcher = PageMatcher(similarity_threshold=0.5)  # Lower threshold for sparse data

        schema1 = FormSchema(
            page_identifier="page-1",
            form_name="Application",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application"],
            ),
        )

        schema2 = FormSchema(
            page_identifier="page-2",
            form_name="Application",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application"],
            ),
        )

        schema3 = FormSchema(
            page_identifier="page-3",
            form_name="Contact",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://other.gov/contact",
                timestamp=None,
                page_headings=["Contact"],
            ),
        )

        matches = matcher.find_all_matches([schema1, schema2, schema3])

        # Should find 1 match: (0, 1) for schema1-schema2
        assert len(matches) == 1
        assert matches[0][0] == 0
        assert matches[0][1] == 1
        assert matches[0][2] > 0.5
