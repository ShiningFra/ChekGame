"""
card_images.py — Mapping Card → numéro d'image (1.jpg à 54.jpg)

Ordre des images :
  ♠  :  1–13  (A,2,3,4,5,6,7,8,9,10,J,Q,K)
  ♥  : 14–26
  ♦  : 27–39
  ♣  : 40–52
  Joker : 53, 54
"""

from game import Card, SUITS

# Valeurs dans l'ordre des images
VALUES_ORDER = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

# Offset de départ pour chaque couleur
SUIT_OFFSET = {
    "spades":   1,
    "hearts":  14,
    "diamonds": 27,
    "clubs":   40,
}

_joker_counter = [0]  # pour alterner 53 / 54

def card_to_image_number(card: Card) -> int:
    """Retourne le numéro de fichier image (1-54) pour une carte donnée."""
    if card.value == "JOKER":
        # Alterne 53 et 54 pour les deux jokers
        n = 53 + (_joker_counter[0] % 2)
        _joker_counter[0] += 1
        return n
    offset = SUIT_OFFSET[card.suit]
    index = VALUES_ORDER.index(card.value)
    return offset + index

def card_to_image_filename(card: Card) -> str:
    """Retourne le nom de fichier, ex: '7.jpg'"""
    return f"{card_to_image_number(card)}.jpg"


# ── Table complète pour vérification ─────────────────────
if __name__ == "__main__":
    from game import build_deck, Card
    deck = []
    from game import SUITS, VALUES
    for suit in SUITS:
        for value in ["A","2","3","4","5","6","7","8","9","10","J","Q","K"]:
            deck.append(Card(value=value, suit=suit))
    deck.append(Card(value="JOKER", suit="joker"))
    deck.append(Card(value="JOKER", suit="joker"))

    for card in deck:
        print(f"{card_to_image_number(card):>2}  →  {card}")
