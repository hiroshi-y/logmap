"""Approximate US state lookup by latitude/longitude.

Uses bounding boxes for each US state. When a point falls within multiple
boxes (common near borders due to non-rectangular state shapes), the state
with the smallest bounding-box area wins — this gives correct results for
most amateur radio grid-square centers.
"""

# (state_code, lat_min, lat_max, lon_min, lon_max)
_STATE_BBOXES = [
    ("AL", 30.15, 35.01, -88.48, -84.89),
    ("AK", 51.20, 71.41, -179.15, -129.98),
    ("AZ", 31.33, 37.01, -114.82, -109.04),
    ("AR", 33.00, 36.50, -94.62, -89.64),
    ("CA", 32.53, 42.01, -124.42, -114.13),
    ("CO", 36.99, 41.01, -109.06, -102.04),
    ("CT", 40.95, 42.05, -73.73, -71.78),
    ("DE", 38.45, 39.84, -75.79, -75.04),
    ("FL", 24.52, 31.01, -87.63, -80.03),
    ("GA", 30.36, 35.00, -85.61, -80.84),
    ("HI", 18.91, 22.24, -160.25, -154.80),
    ("ID", 42.00, 49.01, -117.25, -111.04),
    ("IL", 36.97, 42.51, -91.52, -87.01),
    ("IN", 37.77, 41.76, -88.10, -84.78),
    ("IA", 40.37, 43.50, -96.64, -90.14),
    ("KS", 36.99, 40.01, -102.05, -94.59),
    ("KY", 36.50, 39.15, -89.57, -81.96),
    ("LA", 28.93, 33.02, -94.05, -88.76),
    ("ME", 43.06, 47.46, -71.09, -66.95),
    ("MD", 37.89, 39.72, -79.49, -75.04),
    ("MA", 41.24, 42.89, -73.51, -69.93),
    ("MI", 41.70, 48.31, -90.42, -82.12),
    ("MN", 43.50, 49.38, -97.24, -89.49),
    ("MS", 30.17, 35.01, -91.66, -88.10),
    ("MO", 35.99, 40.62, -95.77, -89.10),
    ("MT", 44.36, 49.01, -116.05, -104.03),
    ("NE", 39.99, 43.01, -104.06, -95.31),
    ("NV", 34.99, 42.01, -120.01, -114.04),
    ("NH", 42.70, 45.31, -72.56, -70.61),
    ("NJ", 38.93, 41.36, -75.56, -73.89),
    ("NM", 31.33, 37.01, -109.05, -103.00),
    ("NY", 40.50, 45.02, -79.76, -71.85),
    ("NC", 33.84, 36.59, -84.33, -75.46),
    ("ND", 45.94, 49.01, -104.06, -96.55),
    ("OH", 38.40, 42.01, -84.82, -80.52),
    ("OK", 33.62, 37.01, -103.01, -94.43),
    ("OR", 41.99, 46.29, -124.57, -116.46),
    ("PA", 39.72, 42.27, -80.53, -74.69),
    ("RI", 41.15, 42.02, -71.86, -71.12),
    ("SC", 32.03, 35.22, -83.36, -78.54),
    ("SD", 42.48, 45.95, -104.06, -96.43),
    ("TN", 34.98, 36.68, -90.31, -81.65),
    ("TX", 25.83, 36.51, -106.65, -93.51),
    ("UT", 36.99, 42.01, -114.05, -109.04),
    ("VT", 42.72, 45.02, -73.44, -71.46),
    ("VA", 36.54, 39.47, -83.68, -75.24),
    ("WA", 45.54, 49.01, -124.85, -116.92),
    ("WV", 37.20, 40.64, -82.65, -77.72),
    ("WI", 42.49, 47.09, -92.89, -86.80),
    ("WY", 40.99, 45.01, -111.06, -104.05),
    ("DC", 38.79, 38.99, -77.12, -76.90),
]


def latlon_to_us_state(lat: float, lon: float) -> str:
    """Return 2-letter US state code for a lat/lon, or empty string.

    When multiple state bounding boxes contain the point (near borders),
    the smallest box wins.
    """
    best_code = ""
    best_area = float("inf")
    for code, lat_min, lat_max, lon_min, lon_max in _STATE_BBOXES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            area = (lat_max - lat_min) * (lon_max - lon_min)
            if area < best_area:
                best_area = area
                best_code = code
    return best_code
