"""Parser for cty.dat (country data file) used in amateur radio.

cty.dat maps callsign prefixes to DXCC entities with lat/lon and other info.
Format reference: https://www.country-files.com/cty-dat-format/
"""

import os
import re
import logging

logger = logging.getLogger(__name__)


class CtyEntity:
    """Represents a single DXCC entity from cty.dat."""

    __slots__ = (
        "name", "cq_zone", "itu_zone", "continent",
        "latitude", "longitude", "utc_offset", "primary_prefix",
    )

    def __init__(self, name: str, cq_zone: int, itu_zone: int,
                 continent: str, latitude: float, longitude: float,
                 utc_offset: float, primary_prefix: str):
        self.name = name
        self.cq_zone = cq_zone
        self.itu_zone = itu_zone
        self.continent = continent
        self.latitude = latitude
        self.longitude = longitude
        self.utc_offset = utc_offset
        self.primary_prefix = primary_prefix


class CtyDat:
    """Parser and lookup for cty.dat file."""

    def __init__(self):
        self._entities: list[CtyEntity] = []
        # Maps exact callsign or prefix -> CtyEntity
        self._exact_calls: dict[str, CtyEntity] = {}
        self._prefixes: dict[str, CtyEntity] = {}

    def load(self, filepath: str) -> None:
        """Load and parse a cty.dat file."""
        if not os.path.exists(filepath):
            logger.error("cty.dat not found: %s", filepath)
            return

        logger.info("Loading cty.dat from %s", filepath)
        with open(filepath, "r", encoding="latin-1") as f:
            content = f.read()

        # cty.dat records: header line followed by prefix lines ending with ;
        # Each record is terminated by ;
        records = content.split(";")

        for record in records:
            record = record.strip()
            if not record:
                continue
            self._parse_record(record)

        logger.info(
            "Loaded %d entities, %d prefixes, %d exact calls",
            len(self._entities), len(self._prefixes), len(self._exact_calls),
        )

    def _parse_record(self, record: str) -> None:
        """Parse a single cty.dat record."""
        lines = record.strip().split("\n")
        if not lines:
            return

        # First line is the header with entity information
        header = lines[0].strip()
        # Remaining lines are prefix aliases
        prefix_lines = "\n".join(lines[1:]) if len(lines) > 1 else ""

        # Parse header: fields separated by colons
        # Format: Entity Name: CQ Zone: ITU Zone: Continent: Lat: Lon: UTC: Primary Prefix:
        parts = [p.strip() for p in header.split(":")]
        if len(parts) < 8:
            return

        try:
            entity = CtyEntity(
                name=parts[0],
                cq_zone=int(parts[1]),
                itu_zone=int(parts[2]),
                continent=parts[3],
                latitude=float(parts[4]),
                longitude=-float(parts[5]),  # cty.dat uses west-positive
                utc_offset=float(parts[6]),
                primary_prefix=parts[7].strip().rstrip("*"),
            )
        except (ValueError, IndexError):
            return

        self._entities.append(entity)
        self._prefixes[entity.primary_prefix.upper()] = entity

        # Parse prefix aliases
        if prefix_lines:
            aliases = prefix_lines.replace("\n", "").split(",")
            for alias in aliases:
                alias = alias.strip().rstrip(";")
                if not alias:
                    continue

                # Handle overrides like =JA1ABC or (4) for zone overrides
                clean = re.sub(r"\(\d+\)", "", alias)  # Remove CQ zone override
                clean = re.sub(r"\[\d+\]", "", clean)  # Remove ITU zone override
                clean = clean.strip()

                if clean.startswith("="):
                    # Exact callsign match
                    self._exact_calls[clean[1:].upper()] = entity
                else:
                    self._prefixes[clean.upper()] = entity

    def lookup(self, callsign: str) -> CtyEntity | None:
        """Look up a callsign and return the matching CtyEntity.

        Tries exact match first, then longest prefix match.
        """
        callsign = callsign.upper().strip()

        # Exact match
        if callsign in self._exact_calls:
            return self._exact_calls[callsign]

        # Longest prefix match
        best_match = None
        best_len = 0
        for prefix, entity in self._prefixes.items():
            if callsign.startswith(prefix) and len(prefix) > best_len:
                best_match = entity
                best_len = len(prefix)

        return best_match

    def get_entity_count(self) -> int:
        return len(self._entities)
