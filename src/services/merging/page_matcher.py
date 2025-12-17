"""Page matching service for identifying duplicate pages across sessions.

Matches pages based on PageIdentification metadata using similarity scoring:
- URL matching (exact or domain-based)
- Heading similarity (page_headings, form_headings)
- Visual section similarity
- Navigation button matching
- Combined similarity threshold
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.lib.logging import get_logger
from src.models.page_identification import PageIdentification
from src.models.schema import FormSchema
from src.models.timestamped import TimestampedValue

logger = get_logger(__name__)


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
        form_similarity_threshold: float = 0.8,
        page_similarity_threshold: float = 0.5,
        debug_dir: Path | str | None = None,
    ):
        """Initialize page matcher with two-stage similarity scoring.

        Two-stage matching approach:
        1. Form Similarity - Are these pages from the same multi-page form?
           Based on: URL, page_headings, structure, navigation
        2. Page Similarity - Are these the same page within that form?
           Based on: form_headings (the actual section titles unique to each page)

        Pages match if they pass BOTH thresholds (same form AND same page).

        Args:
            similarity_threshold: Legacy combined threshold (kept for backwards compatibility)
            form_similarity_threshold: Minimum score to consider pages from same form (0.0-1.0)
            page_similarity_threshold: Minimum score to consider same page within form (0.0-1.0)
            debug_dir: Directory to write debug files. If None, no debug files are generated.
        """
        self.similarity_threshold = similarity_threshold
        self.form_similarity_threshold = form_similarity_threshold
        self.page_similarity_threshold = page_similarity_threshold
        self.debug_dir = Path(debug_dir) if debug_dir else None

        # Form similarity weights (shared across pages in same form)
        self.url_weight = 0.4
        self.page_headings_weight = 0.3
        self.structure_weight = 0.2
        self.navigation_weight = 0.1

        # Debug data collection
        self._debug_comparisons: list[dict[str, Any]] = []

    def _extract_values(
        self, items: list[TimestampedValue[str]] | None
    ) -> list[str]:
        """Extract string values from list of TimestampedValue.

        Used for similarity comparisons where only values matter, not timestamps.

        Args:
            items: List of timestamped values, or None

        Returns:
            List of extracted string values
        """
        if not items:
            return []
        return [item.value for item in items]

    def _extract_value(
        self, item: TimestampedValue[str] | None
    ) -> str | None:
        """Extract value from a TimestampedValue, or return None.

        Used for URL and other scalar property comparisons.

        Args:
            item: Timestamped value, or None

        Returns:
            Extracted string value, or None
        """
        if item is None:
            return None
        return item.value

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

    def compute_page_headings_similarity(
        self, page1: PageIdentification, page2: PageIdentification
    ) -> float:
        """Compute page headings similarity score.

        Page headings are typically shared across pages in the same form flow
        (e.g., "Online Lodgement", "Australian citizenship by descent").

        Extracts values from TimestampedValue wrappers for comparison.

        Args:
            page1: First page identification
            page2: Second page identification

        Returns:
            Page headings similarity score (0.0-1.0)
        """
        values1 = self._extract_values(page1.page_headings)
        values2 = self._extract_values(page2.page_headings)
        return self.compute_list_similarity(values1, values2)

    def compute_form_headings_similarity(
        self, page1: PageIdentification, page2: PageIdentification
    ) -> float:
        """Compute form headings similarity score.

        Form headings are typically unique per page within a form flow.
        High similarity indicates the same page captured multiple times.
        Low similarity indicates different pages in the same flow.

        Extracts values from TimestampedValue wrappers for comparison.

        Args:
            page1: First page identification
            page2: Second page identification

        Returns:
            Form headings similarity score (0.0-1.0)
        """
        values1 = self._extract_values(page1.form_headings)
        values2 = self._extract_values(page2.form_headings)
        return self.compute_list_similarity(values1, values2)

    def compute_structure_similarity(
        self, page1: PageIdentification, page2: PageIdentification
    ) -> float:
        """Compute visual structure similarity.

        Based on visual sections overlap.
        Extracts values from TimestampedValue wrappers for comparison.

        Args:
            page1: First page identification
            page2: Second page identification

        Returns:
            Structure similarity score
        """
        values1 = self._extract_values(page1.visual_sections)
        values2 = self._extract_values(page2.visual_sections)
        return self.compute_list_similarity(values1, values2)

    def compute_navigation_similarity(
        self, page1: PageIdentification, page2: PageIdentification
    ) -> float:
        """Compute navigation button similarity.

        Extracts values from TimestampedValue wrappers for comparison.

        Args:
            page1: First page identification
            page2: Second page identification

        Returns:
            Navigation similarity score
        """
        values1 = self._extract_values(page1.navigation_buttons)
        values2 = self._extract_values(page2.navigation_buttons)
        return self.compute_list_similarity(values1, values2)

    def compute_similarity(
        self, page1: PageIdentification, page2: PageIdentification
    ) -> tuple[float, float, dict[str, float]]:
        """Compute two-stage similarity scores between two pages.

        Two-stage matching:
        1. Form Similarity: Are these pages from the same multi-page form?
           Based on URL, page_headings, structure, navigation (shared across form pages)
        2. Page Similarity: Are these the same page within that form?
           Based on form_headings (unique section titles per page)

        Args:
            page1: First page identification
            page2: Second page identification

        Returns:
            Tuple of (form_similarity, page_similarity, component_scores)
        """
        # Extract values from TimestampedValue wrappers for URL comparison
        url1 = self._extract_value(page1.url)
        url2 = self._extract_value(page2.url)
        url_score = self.compute_url_similarity(url1, url2)
        page_headings_score = self.compute_page_headings_similarity(page1, page2)
        form_headings_score = self.compute_form_headings_similarity(page1, page2)
        structure_score = self.compute_structure_similarity(page1, page2)
        navigation_score = self.compute_navigation_similarity(page1, page2)

        # Form similarity: shared characteristics across pages in same form
        form_similarity = (
            (url_score * self.url_weight)
            + (page_headings_score * self.page_headings_weight)
            + (structure_score * self.structure_weight)
            + (navigation_score * self.navigation_weight)
        )

        # Page similarity: unique characteristics identifying specific page
        page_similarity = form_headings_score

        component_scores = {
            "url": url_score,
            "page_headings": page_headings_score,
            "form_headings": form_headings_score,
            "structure": structure_score,
            "navigation": navigation_score,
        }

        return form_similarity, page_similarity, component_scores

    def are_pages_matching(
        self, schema1: FormSchema, schema2: FormSchema
    ) -> tuple[bool, float, float, dict[str, float]]:
        """Determine if two schemas represent the same page using two-stage matching.

        Two-stage matching:
        1. Form Similarity: Must exceed form_similarity_threshold (same form?)
        2. Page Similarity: Must exceed page_similarity_threshold (same page?)

        Pages match only if BOTH thresholds are met.

        Args:
            schema1: First schema to compare
            schema2: Second schema to compare

        Returns:
            Tuple of (is_match, form_similarity, page_similarity, component_scores)
        """
        form_similarity, page_similarity, components = self.compute_similarity(
            schema1.page_identification, schema2.page_identification
        )

        # Two-stage matching: must pass both thresholds
        same_form = form_similarity >= self.form_similarity_threshold
        same_page = page_similarity >= self.page_similarity_threshold
        is_match = same_form and same_page

        # Collect debug data if debug mode is enabled
        if self.debug_dir is not None:
            self._debug_comparisons.append({
                "schema1": {
                    "page_identifier": schema1.page_identifier.value,
                    "form_name": schema1.form_name.value,
                    "page_identification": self._serialize_page_identification(
                        schema1.page_identification
                    ),
                },
                "schema2": {
                    "page_identifier": schema2.page_identifier.value,
                    "form_name": schema2.form_name.value,
                    "page_identification": self._serialize_page_identification(
                        schema2.page_identification
                    ),
                },
                "two_stage_matching": {
                    "form_similarity": round(form_similarity, 4),
                    "form_threshold": self.form_similarity_threshold,
                    "same_form": same_form,
                    "page_similarity": round(page_similarity, 4),
                    "page_threshold": self.page_similarity_threshold,
                    "same_page": same_page,
                },
                "is_match": is_match,
                "component_scores": {
                    "url": round(components.get("url", 0), 4),
                    "page_headings": round(components.get("page_headings", 0), 4),
                    "form_headings": round(components.get("form_headings", 0), 4),
                    "structure": round(components.get("structure", 0), 4),
                    "navigation": round(components.get("navigation", 0), 4),
                },
                "weighted_contributions_to_form_similarity": {
                    "url": round(components.get("url", 0) * self.url_weight, 4),
                    "page_headings": round(components.get("page_headings", 0) * self.page_headings_weight, 4),
                    "structure": round(components.get("structure", 0) * self.structure_weight, 4),
                    "navigation": round(components.get("navigation", 0) * self.navigation_weight, 4),
                },
            })

        # Debug logging for page matching analysis
        logger.debug(
            "page_match_comparison",
            schema1_id=schema1.page_identifier.value,
            schema1_form_name=schema1.form_name.value,
            schema2_id=schema2.page_identifier.value,
            schema2_form_name=schema2.form_name.value,
            is_match=is_match,
            form_similarity=round(form_similarity, 4),
            form_threshold=self.form_similarity_threshold,
            same_form=same_form,
            page_similarity=round(page_similarity, 4),
            page_threshold=self.page_similarity_threshold,
            same_page=same_page,
            url_score=round(components.get("url", 0), 4),
            page_headings_score=round(components.get("page_headings", 0), 4),
            form_headings_score=round(components.get("form_headings", 0), 4),
            structure_score=round(components.get("structure", 0), 4),
            navigation_score=round(components.get("navigation", 0), 4),
        )

        return is_match, form_similarity, page_similarity, components

    def _serialize_page_identification(
        self, page_id: PageIdentification | None
    ) -> dict[str, Any]:
        """Serialize PageIdentification for debug output.

        Extracts values from TimestampedValue wrappers for readable output.

        Args:
            page_id: PageIdentification to serialize

        Returns:
            Dictionary representation of the page identification (values only)
        """
        if page_id is None:
            return {}

        return {
            "url": self._extract_value(page_id.url),
            "page_headings": self._extract_values(page_id.page_headings),
            "form_headings": self._extract_values(page_id.form_headings),
            "visual_sections": self._extract_values(page_id.visual_sections),
            "navigation_buttons": self._extract_values(page_id.navigation_buttons),
        }

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

        logger.info(
            "page_grouping_start",
            schema_count=len(schemas),
            form_similarity_threshold=self.form_similarity_threshold,
            page_similarity_threshold=self.page_similarity_threshold,
            schema_identifiers=[s.page_identifier.value for s in schemas],
        )

        groups: dict[str, list[FormSchema]] = {}
        processed_indices: set[int] = set()

        for i, schema in enumerate(schemas):
            if i in processed_indices:
                continue

            # Start new group with this schema
            group_id = schema.page_identifier.value
            group = [schema]
            processed_indices.add(i)

            logger.debug(
                "page_group_seed",
                group_id=group_id,
                seed_form_name=schema.form_name.value,
                seed_url=self._extract_value(schema.page_identification.url) if schema.page_identification else None,
                seed_page_headings=self._extract_values(schema.page_identification.page_headings) if schema.page_identification else None,
                seed_form_headings=self._extract_values(schema.page_identification.form_headings) if schema.page_identification else None,
            )

            # Find all matching schemas
            for j, other_schema in enumerate(schemas):
                if j <= i or j in processed_indices:
                    continue

                is_match, form_sim, page_sim, components = self.are_pages_matching(schema, other_schema)

                if is_match:
                    group.append(other_schema)
                    processed_indices.add(j)
                    logger.debug(
                        "page_group_match_added",
                        group_id=group_id,
                        matched_schema_id=other_schema.page_identifier.value,
                        matched_form_name=other_schema.form_name.value,
                        form_similarity=round(form_sim, 4),
                        page_similarity=round(page_sim, 4),
                    )

            groups[group_id] = group

            logger.info(
                "page_group_formed",
                group_id=group_id,
                group_size=len(group),
                member_form_names=[s.form_name.value for s in group],
                member_identifiers=[s.page_identifier.value for s in group],
            )

        logger.info(
            "page_grouping_complete",
            total_schemas=len(schemas),
            groups_formed=len(groups),
            group_sizes={gid: len(members) for gid, members in groups.items()},
        )

        # Write debug file if debug mode is enabled
        if self.debug_dir is not None:
            self._write_debug_file(groups)

        return groups

    def _write_debug_file(self, groups: dict[str, list[FormSchema]]) -> Path:
        """Write debug file with page matching details.

        Creates a JSON file containing:
        - All pairwise comparisons with similarity scores
        - Which comparisons exceeded the threshold
        - Final grouping results

        Args:
            groups: The resulting page groups

        Returns:
            Path to the written debug file
        """
        self.debug_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_file = self.debug_dir / f"page_matching_debug_{timestamp}.json"

        # Separate matches from non-matches for easier reading
        matches = [c for c in self._debug_comparisons if c["is_match"]]
        non_matches = [c for c in self._debug_comparisons if not c["is_match"]]

        debug_data = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "two_stage_matching": {
                    "form_similarity_threshold": self.form_similarity_threshold,
                    "page_similarity_threshold": self.page_similarity_threshold,
                    "description": "Pages match if form_similarity >= form_threshold AND page_similarity >= page_threshold",
                },
                "form_similarity_weights": {
                    "url": self.url_weight,
                    "page_headings": self.page_headings_weight,
                    "structure": self.structure_weight,
                    "navigation": self.navigation_weight,
                },
                "page_similarity_basis": "form_headings (Jaccard similarity)",
                "total_comparisons": len(self._debug_comparisons),
                "matches_found": len(matches),
                "non_matches": len(non_matches),
            },
            "summary": {
                "groups_formed": len(groups),
                "group_details": {
                    group_id: {
                        "size": len(schemas),
                        "members": [
                            {
                                "page_identifier": s.page_identifier.value,
                                "form_name": s.form_name.value,
                            }
                            for s in schemas
                        ],
                    }
                    for group_id, schemas in groups.items()
                },
            },
            "matches": matches,
            "non_matches": non_matches,
            "all_comparisons": self._debug_comparisons,
        }

        with open(debug_file, "w") as f:
            json.dump(debug_data, f, indent=2)

        logger.info(
            "page_matching_debug_file_written",
            debug_file=str(debug_file),
            total_comparisons=len(self._debug_comparisons),
            matches_found=len(matches),
        )

        # Clear debug data for next run
        self._debug_comparisons = []

        return debug_file

    def find_all_matches(
        self, schemas: list[FormSchema]
    ) -> list[tuple[int, int, float, float]]:
        """Find all pairwise matches above threshold.

        Useful for debugging or visualizing the match graph.

        Args:
            schemas: List of schemas to compare

        Returns:
            List of (index1, index2, form_similarity, page_similarity) tuples
        """
        matches = []

        for i in range(len(schemas)):
            for j in range(i + 1, len(schemas)):
                is_match, form_sim, page_sim, _ = self.are_pages_matching(
                    schemas[i], schemas[j]
                )

                if is_match:
                    matches.append((i, j, form_sim, page_sim))

        return matches
