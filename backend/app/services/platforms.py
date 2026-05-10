"""Platform registry — Swiggy-only after the multi-platform retirement.

Bimi orders only through Swiggy MCP (Instamart for groceries, Food for
restaurant meals). Dineout and all non-Swiggy platforms (Zepto, Blinkit,
BigBasket, DMart, JioMart, Flipkart Minutes, Amazon Fresh, Urban Company)
were removed when we committed to the Swiggy Builders Club partnership.

The registry is kept as a small data structure so existing callers
(grocery basket flows, absence flow) continue to work without a complete
rewrite. Loop 5 will rebuild this around the proper Swiggy MCP adapter.
"""

from dataclasses import dataclass


@dataclass
class PlatformConfig:
    id: str
    name: str
    surface: str  # "instamart" | "food"
    mcp_url: str
    icon: str = "🛒"
    delivery_eta: str = ""
    deep_link_template: str | None = None


PLATFORMS: dict[str, PlatformConfig] = {
    "swiggy_instamart": PlatformConfig(
        id="swiggy_instamart",
        name="Swiggy Instamart",
        surface="instamart",
        mcp_url="https://mcp.swiggy.com/im",
        icon="🛒",
        delivery_eta="15-25 min",
        deep_link_template="https://www.swiggy.com/instamart/search?query={query}",
    ),
    "swiggy_food": PlatformConfig(
        id="swiggy_food",
        name="Swiggy Food",
        surface="food",
        mcp_url="https://mcp.swiggy.com/food",
        icon="🍕",
        delivery_eta="25-35 min",
        deep_link_template="https://www.swiggy.com/search?query={query}",
    ),
}


GROCERY_PLATFORM_IDS = ["swiggy_instamart"]
FOOD_PLATFORM_IDS = ["swiggy_food"]
ALL_PLATFORM_IDS = GROCERY_PLATFORM_IDS + FOOD_PLATFORM_IDS


def get_platform(platform_id: str) -> PlatformConfig | None:
    return PLATFORMS.get(platform_id)


def get_all_platforms() -> list[PlatformConfig]:
    return list(PLATFORMS.values())


def get_grocery_platforms() -> list[PlatformConfig]:
    return [PLATFORMS[pid] for pid in GROCERY_PLATFORM_IDS if pid in PLATFORMS]


def get_food_platforms() -> list[PlatformConfig]:
    return [PLATFORMS[pid] for pid in FOOD_PLATFORM_IDS if pid in PLATFORMS]


def get_deeplink_url(platform_id: str, query: str) -> str | None:
    """Build a deep link to a Swiggy surface from a free-text query."""
    import urllib.parse

    p = PLATFORMS.get(platform_id)
    if not p or not p.deep_link_template:
        return None
    return p.deep_link_template.format(query=urllib.parse.quote(query))


def get_replacement_options(role: str, city: str = "bangalore") -> list[dict]:
    """Return third-party fallback options when household help is absent.
    With the multi-platform stack retired, the only fallback is "order food
    instead via Swiggy" for cook absences.
    """
    if role == "cook":
        return [{
            "platform_id": "swiggy_food",
            "platform_name": "Order food from Swiggy",
            "deep_link": "https://www.swiggy.com/restaurants",
            "icon": "🟠",
        }]
    return []
