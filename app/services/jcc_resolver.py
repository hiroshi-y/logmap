"""JCC (Japan Century Cities) code resolver.

Maps JCC codes to city names and approximate coordinates.
JCC codes are used in Japanese amateur radio to identify cities/wards.
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

# Built-in subset of major JCC codes with coordinates.
# A full dataset can be loaded from jcc_codes.json in the data directory.
_BUILTIN_JCC: dict[str, dict] = {
    # Hokkaido
    "0101": {"name": "札幌市", "name_en": "Sapporo", "lat": 43.0621, "lon": 141.3544},
    "0102": {"name": "函館市", "name_en": "Hakodate", "lat": 41.7688, "lon": 140.7290},
    "0103": {"name": "小樽市", "name_en": "Otaru", "lat": 43.1907, "lon": 140.9945},
    "0104": {"name": "旭川市", "name_en": "Asahikawa", "lat": 43.7709, "lon": 142.3650},
    "0105": {"name": "室蘭市", "name_en": "Muroran", "lat": 42.3152, "lon": 140.9739},
    "0106": {"name": "釧路市", "name_en": "Kushiro", "lat": 42.9849, "lon": 144.3820},
    "0107": {"name": "帯広市", "name_en": "Obihiro", "lat": 42.9236, "lon": 143.1966},
    "0108": {"name": "北見市", "name_en": "Kitami", "lat": 43.8030, "lon": 143.8907},
    # Tohoku
    "0201": {"name": "青森市", "name_en": "Aomori", "lat": 40.8246, "lon": 140.7400},
    "0301": {"name": "盛岡市", "name_en": "Morioka", "lat": 39.7036, "lon": 141.1527},
    "0401": {"name": "仙台市", "name_en": "Sendai", "lat": 38.2682, "lon": 140.8694},
    "0501": {"name": "秋田市", "name_en": "Akita", "lat": 39.7200, "lon": 140.1025},
    "0601": {"name": "山形市", "name_en": "Yamagata", "lat": 38.2405, "lon": 140.3634},
    "0701": {"name": "福島市", "name_en": "Fukushima", "lat": 37.7500, "lon": 140.4676},
    # Kanto
    "0801": {"name": "水戸市", "name_en": "Mito", "lat": 36.3414, "lon": 140.4467},
    "0901": {"name": "宇都宮市", "name_en": "Utsunomiya", "lat": 36.5551, "lon": 139.8836},
    "1001": {"name": "前橋市", "name_en": "Maebashi", "lat": 36.3911, "lon": 139.0608},
    "1002": {"name": "高崎市", "name_en": "Takasaki", "lat": 36.3222, "lon": 139.0028},
    "1101": {"name": "さいたま市", "name_en": "Saitama", "lat": 35.8617, "lon": 139.6455},
    "1201": {"name": "千葉市", "name_en": "Chiba", "lat": 35.6073, "lon": 140.1063},
    "1301": {"name": "新宿区", "name_en": "Shinjuku", "lat": 35.6938, "lon": 139.7035},
    "1302": {"name": "港区", "name_en": "Minato", "lat": 35.6581, "lon": 139.7514},
    "1303": {"name": "千代田区", "name_en": "Chiyoda", "lat": 35.6940, "lon": 139.7536},
    "1304": {"name": "中央区", "name_en": "Chuo", "lat": 35.6707, "lon": 139.7720},
    "1305": {"name": "文京区", "name_en": "Bunkyo", "lat": 35.7081, "lon": 139.7522},
    "1306": {"name": "台東区", "name_en": "Taito", "lat": 35.7126, "lon": 139.7800},
    "1307": {"name": "墨田区", "name_en": "Sumida", "lat": 35.7107, "lon": 139.8015},
    "1308": {"name": "江東区", "name_en": "Koto", "lat": 35.6729, "lon": 139.8173},
    "1309": {"name": "品川区", "name_en": "Shinagawa", "lat": 35.6092, "lon": 139.7303},
    "1310": {"name": "目黒区", "name_en": "Meguro", "lat": 35.6414, "lon": 139.6982},
    "1311": {"name": "大田区", "name_en": "Ota", "lat": 35.5613, "lon": 139.7160},
    "1312": {"name": "世田谷区", "name_en": "Setagaya", "lat": 35.6462, "lon": 139.6532},
    "1313": {"name": "渋谷区", "name_en": "Shibuya", "lat": 35.6640, "lon": 139.6982},
    "1314": {"name": "中野区", "name_en": "Nakano", "lat": 35.7078, "lon": 139.6638},
    "1315": {"name": "杉並区", "name_en": "Suginami", "lat": 35.6996, "lon": 139.6366},
    "1316": {"name": "豊島区", "name_en": "Toshima", "lat": 35.7263, "lon": 139.7176},
    "1317": {"name": "北区", "name_en": "Kita", "lat": 35.7528, "lon": 139.7373},
    "1318": {"name": "荒川区", "name_en": "Arakawa", "lat": 35.7365, "lon": 139.7832},
    "1319": {"name": "板橋区", "name_en": "Itabashi", "lat": 35.7512, "lon": 139.7094},
    "1320": {"name": "練馬区", "name_en": "Nerima", "lat": 35.7355, "lon": 139.6517},
    "1321": {"name": "足立区", "name_en": "Adachi", "lat": 35.7748, "lon": 139.8044},
    "1322": {"name": "葛飾区", "name_en": "Katsushika", "lat": 35.7437, "lon": 139.8474},
    "1323": {"name": "江戸川区", "name_en": "Edogawa", "lat": 35.7068, "lon": 139.8682},
    "1401": {"name": "横浜市", "name_en": "Yokohama", "lat": 35.4437, "lon": 139.6380},
    "1402": {"name": "川崎市", "name_en": "Kawasaki", "lat": 35.5309, "lon": 139.7030},
    "1403": {"name": "横須賀市", "name_en": "Yokosuka", "lat": 35.2814, "lon": 139.6722},
    # Chubu
    "1501": {"name": "新潟市", "name_en": "Niigata", "lat": 37.9026, "lon": 139.0233},
    "1601": {"name": "富山市", "name_en": "Toyama", "lat": 36.6953, "lon": 137.2113},
    "1701": {"name": "金沢市", "name_en": "Kanazawa", "lat": 36.5613, "lon": 136.6562},
    "1801": {"name": "福井市", "name_en": "Fukui", "lat": 36.0652, "lon": 136.2219},
    "1901": {"name": "甲府市", "name_en": "Kofu", "lat": 35.6642, "lon": 138.5684},
    "2001": {"name": "長野市", "name_en": "Nagano", "lat": 36.6513, "lon": 138.1810},
    "2101": {"name": "岐阜市", "name_en": "Gifu", "lat": 35.4233, "lon": 136.7606},
    "2201": {"name": "静岡市", "name_en": "Shizuoka", "lat": 34.9769, "lon": 138.3831},
    "2202": {"name": "浜松市", "name_en": "Hamamatsu", "lat": 34.7108, "lon": 137.7261},
    "2301": {"name": "名古屋市", "name_en": "Nagoya", "lat": 35.1815, "lon": 136.9066},
    # Kinki
    "2401": {"name": "津市", "name_en": "Tsu", "lat": 34.7303, "lon": 136.5086},
    "2501": {"name": "大津市", "name_en": "Otsu", "lat": 35.0045, "lon": 135.8686},
    "2601": {"name": "京都市", "name_en": "Kyoto", "lat": 35.0116, "lon": 135.7681},
    "2701": {"name": "大阪市", "name_en": "Osaka", "lat": 34.6937, "lon": 135.5023},
    "2801": {"name": "神戸市", "name_en": "Kobe", "lat": 34.6901, "lon": 135.1956},
    "2901": {"name": "奈良市", "name_en": "Nara", "lat": 34.6851, "lon": 135.8049},
    "3001": {"name": "和歌山市", "name_en": "Wakayama", "lat": 34.2306, "lon": 135.1707},
    # Chugoku
    "3101": {"name": "鳥取市", "name_en": "Tottori", "lat": 35.5011, "lon": 134.2351},
    "3201": {"name": "松江市", "name_en": "Matsue", "lat": 35.4723, "lon": 133.0505},
    "3301": {"name": "岡山市", "name_en": "Okayama", "lat": 34.6618, "lon": 133.9344},
    "3401": {"name": "広島市", "name_en": "Hiroshima", "lat": 34.3853, "lon": 132.4553},
    "3501": {"name": "山口市", "name_en": "Yamaguchi", "lat": 34.1861, "lon": 131.4707},
    # Shikoku
    "3601": {"name": "徳島市", "name_en": "Tokushima", "lat": 34.0658, "lon": 134.5593},
    "3701": {"name": "高松市", "name_en": "Takamatsu", "lat": 34.3401, "lon": 134.0434},
    "3801": {"name": "松山市", "name_en": "Matsuyama", "lat": 33.8392, "lon": 132.7657},
    "3901": {"name": "高知市", "name_en": "Kochi", "lat": 33.5597, "lon": 133.5311},
    # Kyushu / Okinawa
    "4001": {"name": "北九州市", "name_en": "Kitakyushu", "lat": 33.8834, "lon": 130.8752},
    "4002": {"name": "福岡市", "name_en": "Fukuoka", "lat": 33.5902, "lon": 130.4017},
    "4101": {"name": "佐賀市", "name_en": "Saga", "lat": 33.2494, "lon": 130.2988},
    "4201": {"name": "長崎市", "name_en": "Nagasaki", "lat": 32.7503, "lon": 129.8777},
    "4301": {"name": "熊本市", "name_en": "Kumamoto", "lat": 32.7898, "lon": 130.7417},
    "4401": {"name": "大分市", "name_en": "Oita", "lat": 33.2382, "lon": 131.6126},
    "4501": {"name": "宮崎市", "name_en": "Miyazaki", "lat": 31.9111, "lon": 131.4239},
    "4601": {"name": "鹿児島市", "name_en": "Kagoshima", "lat": 31.5966, "lon": 130.5571},
    "4701": {"name": "那覇市", "name_en": "Naha", "lat": 26.3344, "lon": 127.6809},
}


class JccResolver:
    """Resolve JCC codes to city names and coordinates."""

    def __init__(self):
        self._codes: dict[str, dict] = dict(_BUILTIN_JCC)

    def load_from_file(self, filepath: str) -> None:
        """Load additional JCC codes from a JSON file."""
        if not os.path.exists(filepath):
            logger.warning("JCC data file not found: %s (using built-in data)", filepath)
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._codes.update(data)
            logger.info("Loaded %d JCC codes from %s", len(data), filepath)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load JCC data: %s", e)

    def lookup(self, jcc_code: str) -> dict | None:
        """Look up a JCC code and return city info.

        Returns dict with keys: name, name_en, lat, lon
        or None if not found.
        """
        code = jcc_code.strip().replace("-", "")
        # Try 4-digit code first
        if code in self._codes:
            return self._codes[code]
        # Try with leading zeros
        if len(code) < 4:
            code = code.zfill(4)
            if code in self._codes:
                return self._codes[code]
        return None

    def get_count(self) -> int:
        return len(self._codes)
