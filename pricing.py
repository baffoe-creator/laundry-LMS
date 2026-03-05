#!/usr/bin/env python3
"""
pricing.py

Static price list data structure for LMS.

This module serves as the single source of truth for the pricing catalogue.
It provides a list of items with their prices for three service types:
- Laundry - Coloured
- Laundry - White
- Pressing / Ironing Only

The data structure is a list of dictionaries with keys:
    item_name: str
    price_coloured: float or None
    price_white: float or None
    price_pressing: float or None

This module is used by database.py to seed the price_catalogue table.
"""

from typing import List, Dict, Union, Optional

# Price list extracted from PRICING_-NEW_INVOICING_MODEL_2022.xlsx
# Format: item_name, price_coloured, price_white, price_pressing
PRICE_CATALOGUE: List[Dict[str, Union[str, Optional[float]]]] = [
    {"item_name": "SHIRTS", "price_coloured": 13.00, "price_white": 15.00, "price_pressing": 10.00},
    {"item_name": "T-SHIRTS & POLO SHIRTS", "price_coloured": 9.00, "price_white": 11.00, "price_pressing": 9.00},
    {"item_name": "TROUSERS", "price_coloured": 13.00, "price_white": 15.00, "price_pressing": 10.00},
    {"item_name": "SHORTS (JEANS / KHAKI)", "price_coloured": 9.00, "price_white": 11.00, "price_pressing": 9.00},
    {"item_name": "JACKET", "price_coloured": 24.00, "price_white": 29.00, "price_pressing": 18.00},
    {"item_name": "SWEATER", "price_coloured": 15.00, "price_white": 17.00, "price_pressing": 10.00},
    {"item_name": "MENS & LADIES SUITS", "price_coloured": 45.00, "price_white": 50.00, "price_pressing": 27.00},
    {"item_name": "CAFTAN / JARABIA", "price_coloured": 24.00, "price_white": 26.00, "price_pressing": 18.00},
    {"item_name": "LADIES SKIRT", "price_coloured": 12.00, "price_white": 14.00, "price_pressing": 9.00},
    {"item_name": "LADIES LONG SKIRT", "price_coloured": 14.00, "price_white": 16.00, "price_pressing": 12.00},
    {"item_name": "BLOUSE / LADIES TOP", "price_coloured": 12.00, "price_white": 14.00, "price_pressing": 8.00},
    {"item_name": "LADIES STRAIGHT DRESS", "price_coloured": 19.00, "price_white": 22.00, "price_pressing": 13.00},
    {"item_name": "LADIES STRAIGHT DRESS (GOWN FORM)", "price_coloured": 35.00, "price_white": 40.00, "price_pressing": 20.00},
    {"item_name": "WEDDING GOWN", "price_coloured": 170.00, "price_white": 220.00, "price_pressing": 120.00},
    {"item_name": "CHOIR ROBE / LAB COAT / GRADUATION GOWN", "price_coloured": 24.00, "price_white": 29.00, "price_pressing": 14.00},
    {"item_name": "KABA KENTE (TOP & DOWN)", "price_coloured": 26.00, "price_white": 30.00, "price_pressing": 14.00},
    {"item_name": "KABA / BOUBOU (TOP & DOWN) NORMAL MATERIAL", "price_coloured": 22.00, "price_white": 24.00, "price_pressing": 12.00},
    {"item_name": "KABA WITH CLOTH", "price_coloured": 23.00, "price_white": 25.00, "price_pressing": 13.00},
    {"item_name": "SMOCK (TOP)", "price_coloured": 24.00, "price_white": 29.00, "price_pressing": 14.00},
    {"item_name": "SMOCK (TOP & DOWN)", "price_coloured": 45.00, "price_white": 55.00, "price_pressing": 25.00},
    {"item_name": "KENTE (MENS CLOTH)", "price_coloured": 40.00, "price_white": 45.00, "price_pressing": 22.00},
    {"item_name": "MENS CLOTH (NORMAL MATERIAL)", "price_coloured": 28.00, "price_white": 33.00, "price_pressing": 15.00},
    {"item_name": "SCARF AND CAP", "price_coloured": 7.00, "price_white": 8.00, "price_pressing": 7.00},
    {"item_name": "SUIT VEST", "price_coloured": 8.00, "price_white": 9.00, "price_pressing": 8.00},
    {"item_name": "BED SPREAD (KING / QUEEN SIZE)", "price_coloured": 22.00, "price_white": 24.00, "price_pressing": 14.00},
    {"item_name": "BED SHEET (KING / QUEEN SIZE)", "price_coloured": 22.00, "price_white": 24.00, "price_pressing": 14.00},
    {"item_name": "PILLOW CASE", "price_coloured": 7.00, "price_white": 8.00, "price_pressing": 6.00},
    {"item_name": "BLANKET (STANDARD SIZE)", "price_coloured": 40.00, "price_white": 50.00, "price_pressing": None},
    {"item_name": "DUVET / COMFORTER (KING / QUEEN SIZE)", "price_coloured": 70.00, "price_white": 80.00, "price_pressing": None},
    {"item_name": "BED COVER", "price_coloured": 35.00, "price_white": 40.00, "price_pressing": None},
    {"item_name": "TOWEL (SMALL & MEDIUM)", "price_coloured": 12.00, "price_white": 14.00, "price_pressing": 7.00},
    {"item_name": "TOWEL (LARGE)", "price_coloured": 19.00, "price_white": 22.00, "price_pressing": 12.00},
    {"item_name": "TABLE CLOTH (STANDARD)", "price_coloured": 14.00, "price_white": 16.00, "price_pressing": 12.00},
    {"item_name": "CURTAINS (STANDARD)", "price_coloured": 19.00, "price_white": 25.00, "price_pressing": 12.00},
    {"item_name": "CURTAINS (ONE/HALF MEDIUM)", "price_coloured": 25.00, "price_white": 29.00, "price_pressing": 17.00},
    {"item_name": "CURTAIN (LARGE)", "price_coloured": 32.00, "price_white": 37.00, "price_pressing": 22.00},
    {"item_name": "PILLOW ITSELF", "price_coloured": 14.00, "price_white": 16.00, "price_pressing": None},
    {"item_name": "CUSHION COVERS / CAR SEAT COVERS", "price_coloured": 13.00, "price_white": 15.00, "price_pressing": None},
    {"item_name": "DOOR MAT", "price_coloured": 10.00, "price_white": 11.00, "price_pressing": None},
    {"item_name": "BAGS (SCHOOL / TRAVELLING)", "price_coloured": 20.00, "price_white": 25.00, "price_pressing": None},
    {"item_name": "SINGLETS, SOCKS, HANDKERCHIEFS, BOXER SHORTS", "price_coloured": 7.00, "price_white": 9.00, "price_pressing": 5.00},
    {"item_name": "KIDS ITEMS", "price_coloured": 11.00, "price_white": 13.00, "price_pressing": 7.00},
    {"item_name": "BABY COAT COVER (SMALL / MEDIUM)", "price_coloured": 12.00, "price_white": 14.00, "price_pressing": None},
    {"item_name": "BABY COAT COVER (LARGE)", "price_coloured": 14.00, "price_white": 16.00, "price_pressing": None},
]


def get_price_catalogue() -> List[Dict[str, Union[str, Optional[float]]]]:
    """
    Return the complete price catalogue.
    """
    return PRICE_CATALOGUE.copy()


def get_item_names() -> List[str]:
    """
    Return a list of all item names for dropdown population.
    """
    return [item["item_name"] for item in PRICE_CATALOGUE]


def get_price_for_item(item_name: str, service_type: str) -> Optional[float]:
    """
    Get the price for a specific item and service type.
    service_type should be one of: 'coloured', 'white', 'pressing'
    """
    for item in PRICE_CATALOGUE:
        if item["item_name"] == item_name:
            if service_type.lower() == "coloured":
                return item["price_coloured"]
            elif service_type.lower() == "white":
                return item["price_white"]
            elif service_type.lower() == "pressing":
                return item["price_pressing"]
    return None