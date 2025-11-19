"""Page matching service for identifying duplicate pages across sessions.

Matches pages based on PageIdentification metadata using similarity scoring:
- URL matching (exact or domain-based)
- Heading similarity (page_headings, form_headings)
- Visual section similarity
- Navigation button matching
- Combined similarity threshold
"""

from dataclasses import dataclass
from typing import Any

from src.models.page_identification import PageIdentification
from src.models.schema import FormSchema


@dataclass
class PageMatch:
    """Represents a match between two pages."""

    page1_id: str
    page2_id: str
    similarity_score: float
    match_details: dict[str, Any]


class PageMatcher:
    """Intelligent page matching using PageIdentification metadata.

    Matches pages based on multiple signals:
    - URL similarity (domain, path, query params)
    - Heading overlap (page headings, form headings)
    - Visual structure (sections, navigation)
    - Combined weighted similarity score

    Example:
        matcher = PageMatcher(url_weight=0.4, heading_weight=0.4)
        groups = matcher.group_schemas_by_page([schema1, schema2, schema3])
        # Returns: {"page_id_1": [schema1, schema2], "page_id_2": [schema3]}
    """

    def __init__(
        self,
        similarity_threshold: float = 0.7,
        url_weight: float = 0.4,
        heading_weight: float = 0.3,
        structure_weight: float = 0.2,
        navigation_weight: float = 0.1,
    ):
        """Initialize page matcher with weighted similarity scoring.

        Args:
            similarity_threshold: Minimum score to consider pages matching (0.0-1.0)
            url_weight: Weight for URL similarity component
            heading_weight: Weight for heading similarity component
            structure_weight: Weight for visual structure similarity
            navigation_weight: Weight for navigation button similarity
        """
        self.similarity_threshold = similarity_threshold
        self.url_weight = url_weight
        self.heading_weight = heading_weight
        self.structure_weight = structure_weight
        self.navigation_weight = navigation_weight

        # Validate weights sum to 1.0
        total_weight = url_weight + heading_weight + structure_weight + navigation_weight
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total_weight}")

    def compute_url_similarity(self, url1: str | None, url2: str | None) -> float:
        """Compute URL similarity score.

        Scoring:
        - Exact match: 1.0
        - Same domain + path: 0.9
        - Same domain, different path: 0.5
        - Different domains: 0.0
        - Either URL missing: 0.0

        Args:
            url1: First URL to compare
            url2: Second URL to compare

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not url1 or not url2:
            return 0.0

        if url1 == url2:
            return 1.0

        # Extract domain and path
        try:
            from urllib.parse import urlparse

            parsed1 = urlparse(url1)
            parsed2 = urlparse(url2)

            # Same domain and path
            if parsed1.netloc == parsed2.netloc and parsed1.path == parsed2.path:
                return 0.9

            # Same domain, different path
            if parsed1.netloc == parsed2.netloc:
                return 0.5

            # Different domains
            return 0.0

        except Exception:
            # If URL parsing fails, fall back to string comparison
            return 1.0 if url1 == url2 else 0.0

    def compute_list_similarity(
        self, list1: list[str] | None, list2: list[str] | None
    ) -> float:
        """Compute similarity between two lists of strings using Jaccard index.

        Args:
            list1: First list to compare
            list2: Second list to compare

        Returns:
            Jaccard similarity score between 0.0 and 1.0
        """
        if not list1 or not list2:
            return 0.0

        set1 = set(list1)
        set2 = set(list2)

        if not set1 and not set2:
            return 1.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def compute_heading_similarity(
        self, page1: PageIdentification, page2: PageIdentification
    ) -> float:
        """Compute heading similarity score.

        Combines:
        - Page headings similarity (60%)
        - Form headings similarity (40%)

        Args:
            page1: First page identification
            page2: Second page identification

        Returns:
            Combined heading similarity score
        """
        page_heading_sim = self.compute_list_similarity(
            page1.page_headings, page2.page_headings
        )
        form_heading_sim = self.compute_list_similarity(
            page1.form_headings, page2.form_headings
        )

        return (page_heading_sim * 0.6) + (form_heading_sim * 0.4)

    def compute_structure_similarity(
        self, page1: PageIdentification, page2: PageIdentification
    ) -> float:
        """Compute visual structure similarity.

        Based on visual sections overlap.

        Args:
            page1: First page identification
            page2: Second page identification

        Returns:
            Structure similarity score
        """
        return self.compute_list_similarity(
            page1.visual_sections, page2.visual_sections
        )

    def compute_navigation_similarity(
        self, page1: PageIdentification, page2: PageIdentification
    ) -> float:
        """Compute navigation button similarity.

        Args:
            page1: First page identification
            page2: Second page identification

        Returns:
            Navigation similarity score
        """
        return self.compute_list_similarity(
            page1.navigation_buttons, page2.navigation_buttons
        )

    def compute_similarity(
        self, page1: PageIdentification, page2: PageIdentification
    ) -> tuple[float, dict[str, float]]:
        """Compute overall similarity score between two pages.

        Args:
            page1: First page identification
            page2: Second page identification

        Returns:
            Tuple of (overall_score, component_scores)
        """
        url_score = self.compute_url_similarity(page1.url, page2.url)
        heading_score = self.compute_heading_similarity(page1, page2)
        structure_score = self.compute_structure_similarity(page1, page2)
        navigation_score = self.compute_navigation_similarity(page1, page2)

        overall_score = (
            (url_score * self.url_weight)
            + (heading_score * self.heading_weight)
            + (structure_score * self.structure_weight)
            + (navigation_score * self.navigation_weight)
        )

        component_scores = {
            "url": url_score,
            "headings": heading_score,
            "structure": structure_score,
            "navigation": navigation_score,
        }

        return overall_score, component_scores

    def are_pages_matching(
        self, schema1: FormSchema, schema2: FormSchema
    ) -> tuple[bool, float, dict[str, float]]:
        """Determine if two schemas represent the same page.

        Args:
            schema1: First schema to compare
            schema2: Second schema to compare

        Returns:
            Tuple of (is_match, similarity_score, component_scores)
        """
        similarity, components = self.compute_similarity(
            schema1.page_identification, schema2.page_identification
        )

        is_match = similarity >= self.similarity_threshold

        return is_match, similarity, components

    def group_schemas_by_page(
        self, schemas: list[FormSchema]
    ) -> dict[str, list[FormSchema]]:
        """Group schemas by matched page identity.

        Uses greedy clustering:
        1. Start with first schema as seed for group
        2. Add all matching schemas to same group
        3. Use remaining schemas to seed new groups
        4. Repeat until all schemas grouped

        Args:
            schemas: List of schemas to group

        Returns:
            Dictionary mapping page_identifier to list of matching schemas

        Example:
            Input: [schema1, schema2, schema3, schema4]
            Output: {
                "page-1": [schema1, schema2],  # Matching pages
                "page-3": [schema3],           # Unique page
                "page-4": [schema4]            # Unique page
            }
        """
        if not schemas:
            return {}

        groups: dict[str, list[FormSchema]] = {}
        processed_indices: set[int] = set()

        for i, schema in enumerate(schemas):
            if i in processed_indices:
                continue

            # Start new group with this schema
            group_id = schema.page_identifier
            group = [schema]
            processed_indices.add(i)

            # Find all matching schemas
            for j, other_schema in enumerate(schemas):
                if j <= i or j in processed_indices:
                    continue

                is_match, similarity, _ = self.are_pages_matching(schema, other_schema)

                if is_match:
                    group.append(other_schema)
                    processed_indices.add(j)

            groups[group_id] = group

        return groups

    def find_all_matches(
        self, schemas: list[FormSchema]
    ) -> list[tuple[int, int, float]]:
        """Find all pairwise matches above threshold.

        Useful for debugging or visualizing the match graph.

        Args:
            schemas: List of schemas to compare

        Returns:
            List of (index1, index2, similarity_score) tuples
        """
        matches = []

        for i in range(len(schemas)):
            for j in range(i + 1, len(schemas)):
                is_match, similarity, _ = self.are_pages_matching(
                    schemas[i], schemas[j]
                )

                if is_match:
                    matches.append((i, j, similarity))

        return matches
