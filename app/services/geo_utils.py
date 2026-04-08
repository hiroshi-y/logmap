"""Geographic utilities: grid square conversion, distance calculation."""

import math


def grid_to_latlon(grid: str) -> tuple[float, float] | None:
    """Convert a Maidenhead grid square to latitude/longitude (center of grid).

    Supports 4-char (e.g. PM95) and 6-char (e.g. PM95ss) locators.
    Returns (latitude, longitude) or None if invalid.
    """
    grid = grid.strip()
    if len(grid) < 4:
        return None

    try:
        grid = grid[:2].upper() + grid[2:]

        lon = (ord(grid[0]) - ord("A")) * 20 - 180
        lat = (ord(grid[1]) - ord("A")) * 10 - 90
        lon += int(grid[2]) * 2
        lat += int(grid[3]) * 1

        if len(grid) >= 6:
            lon += (ord(grid[4].lower()) - ord("a")) * (2 / 24)
            lat += (ord(grid[5].lower()) - ord("a")) * (1 / 24)
            # Center of sub-square
            lon += 1 / 24
            lat += 0.5 / 24
        else:
            # Center of main square
            lon += 1
            lat += 0.5

        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return (lat, lon)
    except (IndexError, ValueError):
        pass
    return None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def latlon_to_grid(lat: float, lon: float) -> str:
    """Convert latitude/longitude to a 6-character Maidenhead grid locator."""
    lon += 180
    lat += 90

    field_lon = int(lon / 20)
    field_lat = int(lat / 10)

    square_lon = int((lon - field_lon * 20) / 2)
    square_lat = int(lat - field_lat * 10)

    subsq_lon = int((lon - field_lon * 20 - square_lon * 2) / (2 / 24))
    subsq_lat = int((lat - field_lat * 10 - square_lat) / (1 / 24))

    return (
        chr(ord("A") + field_lon)
        + chr(ord("A") + field_lat)
        + str(square_lon)
        + str(square_lat)
        + chr(ord("a") + subsq_lon)
        + chr(ord("a") + subsq_lat)
    )
