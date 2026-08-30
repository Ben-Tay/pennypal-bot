from __future__ import annotations

import re

CATEGORIES = [
    "Food & Drinks",
    "Groceries",
    "Transport",
    "Bills & Utilities",
    "Rent",
    "Shopping",
    "Entertainment",
    "Health & Fitness",
    "Travel",
    "Education",
    "Gifts & Donations",
    "Others",
]

KEYWORDS = {
    "Food & Drinks": [
        "kopi", "kaya toast", "coffee", "cafe", "starbucks", "kfc", "mcdonald", "mcd",
        "burger", "pizza", "lunch", "dinner", "breakfast", "brunch", "supper", "hawker",
        "food court", "food", "meal", "restaurant", "tea", "boba", "bubble tea", "milk tea",
        "dessert", "cake", "ice cream", "snack", "sushi", "ramen", "mala", "hotpot", "bbq",
        "prata", "laksa", "bak chor", "nasi", "satay", "dim sum", "buffet", "takeaway",
        "dabao", "juice", "smoothie", "beer", "wine", "cocktail", "drink",
    ],
    "Groceries": [
        "fairprice", "ntuc", "giant", "sheng shiong", "cold storage", "cs fresh",
        "donki", "don don ki", "grocery", "groceries", "supermarket", "wet market", "market run",
    ],
    "Transport": [
        "grab", "gojek", "ryde", "tada", "mrt", "smrt", "lrt", "bus", "taxi", "cab",
        "uber", "comfort", "petrol", "fuel", "shell station", "caltex", "esso", "erp",
        "parking", "season parking", "transport", "train fare", "commute", "top up ezlink",
        "ezlink", "nets flash",
    ],
    "Bills & Utilities": [
        "bill", "bills", "utilities", "electricity", "electric", "water bill", "gas bill",
        "internet", "broadband", "wifi", "mobile", "phone bill", "singtel", "starhub",
        "m1", "simba", "myrepublic", "viewqwest", "telco", "sp services", "insurance",
        "premium", "subscription fee", "service fee",
    ],
    "Rent": [
        "rent", "rental", "mortgage", "housing loan", "hdb", "condo", "room rent", "agent fee",
    ],
    "Shopping": [
        "shopee", "lazada", "amazon", "taobao", "shein", "temu", "uniqlo", "zara", "h&m",
        "nike", "adidas", "decathlon", "ikea", "muji", "daiso", "clothes", "clothing",
        "shirt", "pants", "shorts", "shoes", "sneakers", "bag", "watch", "jewellery",
        "jewelry", "skincare", "cosmetics", "makeup", "perfume", "shopping", "haul",
    ],
    "Entertainment": [
        "netflix", "disney+", "disney plus", "hbo", "prime video", "spotify", "youtube premium",
        "apple music", "deezer", "tidal", "game", "games", "steam", "playstation", "nintendo",
        "xbox", "switch", "movie", "cinema", "golden village", "shaw", "film", "concert",
        "ticket", "musical", "comedy show", "arcade", "karaoke", "ktv", "clubbing", "patreon",
    ],
    "Health & Fitness": [
        "gym", "fitness", "yoga", "pilates", "protein", "supplement", "supplements",
        "doctor", "clinic", "dentist", "dental", "medicine", "medication", "pharmacy",
        "guardian", "watsons", "hospital", "physio", "therapy", "counselling", "glasses",
        "contact lenses", "vitamins", "health check",
    ],
    "Travel": [
        "flight", "airfare", "air ticket", "scoot", "airasia", "singapore airlines", "hotel",
        "hostel", "airbnb", "agoda", "booking.com", "staycation", "trip", "travel", "holiday",
        "vacation", "luggage", "tour", "passport", "travel insurance", "visa fee",
    ],
    "Education": [
        "udemy", "coursera", "course", "tuition", "textbook", "textbooks", "books",
        "bookstore", "stationery", "exam fee", "school fees", "kindle", "ebook", "masterclass",
        "language class", "piano lesson", "guitar lesson", "workshop", "seminar",
    ],
    "Gifts & Donations": [
        "gift", "present", "birthday gift", "wedding gift", "ang bao", "angbao", "donation",
        "charity", "offering", "red cross", "church", "temple", "mosque", "fundraiser",
        "congratulatory",
    ],
}

ALIASES = {
    "food": "Food & Drinks", "drinks": "Food & Drinks", "f&b": "Food & Drinks",
    "fd": "Food & Drinks", "fb": "Food & Drinks", "eating out": "Food & Drinks",
    "dining": "Food & Drinks", "coffee": "Food & Drinks",
    "grocery": "Groceries", "groceries": "Groceries", "supermarket": "Groceries",
    "transport": "Transport", "transit": "Transport", "commute": "Transport",
    "car": "Transport", "ride": "Transport",
    "bills": "Bills & Utilities", "utilities": "Bills & Utilities",
    "bill": "Bills & Utilities", "phone": "Bills & Utilities",
    "rent": "Rent", "housing": "Rent", "mortgage": "Rent",
    "shopping": "Shopping", "clothes": "Shopping", "retail": "Shopping",
    "entertainment": "Entertainment", "fun": "Entertainment", "subs": "Entertainment",
    "subscriptions": "Entertainment", "leisure": "Entertainment",
    "health": "Health & Fitness", "fitness": "Health & Fitness", "gym": "Health & Fitness",
    "medical": "Health & Fitness",
    "travel": "Travel", "holiday": "Travel", "vacation": "Travel", "trips": "Travel",
    "education": "Education", "edu": "Education", "learning": "Education", "courses": "Education",
    "gifts": "Gifts & Donations", "gift": "Gifts & Donations", "donation": "Gifts & Donations",
    "donations": "Gifts & Donations", "charity": "Gifts & Donations",
    "others": "Others", "other": "Others", "misc": "Others", "miscellaneous": "Others",
}

TOTAL_KEY = "__total__"

TOTAL_ALIASES = {"total", "overall", "all", "monthly", "everything"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def guess_category(description: str) -> str | None:
    desc = f" {_normalize(description)} "
    for category in CATEGORIES:
        if category == "Others":
            continue
        for keyword in KEYWORDS.get(category, []):
            if keyword in desc:
                return category
    return None


def resolve_category(text: str) -> str | None:
    norm = _normalize(text)
    norm_clean = "".join(ch for ch in norm if ch.isalnum() or ch in "& ")
    norm_clean = re.sub(r"\s+", " ", norm_clean).strip()
    if not norm_clean:
        return None
    if norm_clean in TOTAL_ALIASES:
        return TOTAL_KEY
    for category in CATEGORIES:
        if norm_clean == category.lower():
            return category
    return ALIASES.get(norm_clean)
