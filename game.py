"""
game.py — CheckGame core logic

Deck: standard 52-card deck + 2 Jokers
Suits: spades ♠, hearts ♥, diamonds ♦, clubs ♣
Values: 2,3,4,5,6,7,8,9,10,J,Q,K,A + JOKER

Special cards:
  J    → change suit (wild)
  7    → next player draws 2
  A    → next player skips turn
  2    → phantom card (always playable, top card unchanged)
  JOKER→ change suit + next player draws 4
"""

import random
from dataclasses import dataclass, field
from typing import Optional

# ──────────────────────────────────────────────────────────
SUITS = ["spades", "hearts", "diamonds", "clubs"]
SUIT_EMOJI = {"spades": "♠️", "hearts": "♥️", "diamonds": "♦️", "clubs": "♣️", "joker": "🃏"}
VALUES = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SPECIAL_CARDS = {"J", "7", "A", "2", "JOKER"}

VALUE_DISPLAY = {
    "J": "Valet",
    "Q": "Dame",
    "K": "Roi",
    "A": "As",
    "JOKER": "Joker",
}


# ══════════════════════════════════════════════════════════
# Card
# ══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Card:
    value: str          # "2".."A" or "JOKER"
    suit: str           # "spades" | "hearts" | "diamonds" | "clubs" | "joker"

    def __str__(self):
        if self.value == "JOKER":
            return "Joker 🃏"
        v = VALUE_DISPLAY.get(self.value, self.value)
        return f"{v} {self.suit_emoji()}"

    def suit_emoji(self) -> str:
        return SUIT_EMOJI.get(self.suit, "")

    def to_id(self) -> str:
        return f"{self.value}_{self.suit}"

    @staticmethod
    def from_id(card_id: str) -> "Card":
        parts = card_id.split("_", 1)
        return Card(value=parts[0], suit=parts[1])

    @property
    def is_phantom(self) -> bool:
        """2 = phantom card, plays on anything, top card unchanged."""
        return self.value == "2"

    @property
    def is_wild(self) -> bool:
        return self.value in ("J", "JOKER")

    @property
    def is_attack(self) -> bool:
        return self.value in ("7", "JOKER")

    @property
    def is_skip(self) -> bool:
        return self.value == "A"

    @property
    def draw_count(self) -> int:
        if self.value == "7":
            return 2
        if self.value == "JOKER":
            return 4
        return 0


# ══════════════════════════════════════════════════════════
# Deck builder
# ══════════════════════════════════════════════════════════

def build_deck() -> list[Card]:
    deck = []
    for suit in SUITS:
        for value in VALUES:
            deck.append(Card(value=value, suit=suit))
    # 2 Jokers
    deck.append(Card(value="JOKER", suit="joker"))
    deck.append(Card(value="JOKER", suit="joker"))
    random.shuffle(deck)
    return deck


# ══════════════════════════════════════════════════════════
# Player
# ══════════════════════════════════════════════════════════

@dataclass
class Player:
    user_id: int
    name: str
    hand: list[Card] = field(default_factory=list)

    def remove_card(self, card: Card):
        self.hand.remove(card)

    def add_cards(self, cards: list[Card]):
        self.hand.extend(cards)


# ══════════════════════════════════════════════════════════
# Game
# ══════════════════════════════════════════════════════════

class Game:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.players: list[Player] = []
        self.started = False
        self.deck: list[Card] = []
        self.discard: list[Card] = []
        self.turn_index: int = 0
        self.direction: int = 1          # 1 = clockwise, -1 = counter
        self.pending_suit_chooser: Optional[int] = None  # user_id
        self._current_suit: Optional[str] = None        # overrides top card suit after wild
        self.lobby_message_id: Optional[int] = None

    # ── Setup ──────────────────────────────────────────────

    def add_player(self, user_id: int, name: str) -> bool:
        if any(p.user_id == user_id for p in self.players):
            return False
        self.players.append(Player(user_id=user_id, name=name))
        return True

    def get_player(self, user_id: int) -> Optional[Player]:
        return next((p for p in self.players if p.user_id == user_id), None)

    def start(self):
        self.deck = build_deck()
        random.shuffle(self.players)
        # Deal 5 cards each
        for player in self.players:
            player.hand = [self.deck.pop() for _ in range(5)]
        # Turn up first non-special card
        while True:
            card = self.deck.pop()
            if card.value not in ("J", "JOKER", "2"):  # start with a normal card
                self.discard.append(card)
                break
            self.deck.insert(0, card)
        self.started = True

    # ── State accessors ────────────────────────────────────

    @property
    def top_card(self) -> Card:
        return self.discard[-1]

    @property
    def effective_suit(self) -> str:
        """The suit that must be matched (may be overridden after a wild)."""
        if self._current_suit:
            return self._current_suit
        return self.top_card.suit

    def current_player(self) -> Player:
        return self.players[self.turn_index]

    # ── Playability ────────────────────────────────────────

    def can_play(self, card: Card, user_id: int) -> bool:
        """Return True if this card is legally playable right now."""
        current = self.current_player()
        if current.user_id != user_id:
            return False
        # Phantom 2: always playable
        if card.is_phantom:
            return True
        # Joker or J (wild): always playable
        if card.is_wild:
            return True
        # Same value or same suit
        top = self.top_card
        suit_match = card.suit == self.effective_suit
        value_match = card.value == top.value
        return suit_match or value_match

    # ── Play a card ────────────────────────────────────────

    def play_card(self, user_id: int, card: Card) -> str:
        """
        Apply the card effect.
        Returns a human-readable effect message (may be empty).
        Does NOT advance the turn yet for wilds (suit must be chosen first).
        """
        player = self.get_player(user_id)
        player.remove_card(card)
        effect = ""

        if card.is_phantom:
            # Phantom: discard beneath top card → top card is unchanged
            self.discard.insert(-1, card)
            # Turn advances normally
            self.next_turn()
            return "👻 Carte fantôme ! La carte du dessus reste inchangée."

        # Normal discard
        self.discard.append(card)
        self._current_suit = None  # reset suit override

        if card.value == "7":
            # Attack: next player draws 2
            self._skip_and_draw(2)
            effect = "⚔️ Attaque ! Le joueur suivant pioche 2 cartes et passe son tour."

        elif card.value == "A":
            # Skip: next player loses their turn
            self._skip_turn()
            effect = "⏸️ Pause ! Le joueur suivant passe son tour."

        elif card.value == "J":
            # Wild: choose suit, then next turn
            self.pending_suit_chooser = user_id
            effect = "🎨 Valet ! Choisis une couleur."
            # Do NOT advance turn yet

        elif card.value == "JOKER":
            # Super wild: choose suit + next draws 4
            self.pending_suit_chooser = user_id
            # We'll draw the 4 cards after suit is chosen (flag for later)
            self._joker_pending = True
            effect = "🃏 Joker ! Choisis une couleur. Le suivant piochera 4 cartes."
            # Do NOT advance turn yet

        else:
            self.next_turn()

        return effect

    def set_top_suit(self, suit: str):
        """Called after player picks suit for J or Joker."""
        self._current_suit = suit
        if getattr(self, "_joker_pending", False):
            self._joker_pending = False
            self._skip_and_draw(4)
        else:
            self.next_turn()

    # ── Turn management ────────────────────────────────────

    def next_turn(self):
        n = len(self.players)
        self.turn_index = (self.turn_index + self.direction) % n

    def _skip_turn(self):
        """Advance TWO steps (skip the next player)."""
        n = len(self.players)
        self.turn_index = (self.turn_index + 2 * self.direction) % n

    def _skip_and_draw(self, count: int):
        """Make next player draw `count` cards, then skip them."""
        n = len(self.players)
        victim_index = (self.turn_index + self.direction) % n
        victim = self.players[victim_index]
        drawn = self._deal(count)
        victim.add_cards(drawn)
        # Skip over victim
        self.turn_index = (victim_index + self.direction) % n

    def _deal(self, count: int) -> list[Card]:
        """Draw `count` cards from deck, reshuffling discard if needed."""
        result = []
        for _ in range(count):
            if not self.deck:
                if len(self.discard) <= 1:
                    break  # edge case: no cards at all
                top = self.discard.pop()
                self.deck = self.discard[:]
                random.shuffle(self.deck)
                self.discard = [top]
            result.append(self.deck.pop())
        return result

    def draw_cards(self, user_id: int, count: int) -> list[Card]:
        """Player actively draws cards."""
        player = self.get_player(user_id)
        drawn = self._deal(count)
        player.add_cards(drawn)
        return drawn

    # ── Win condition ──────────────────────────────────────

    def check_winner(self) -> Optional[Player]:
        for p in self.players:
            if len(p.hand) == 0:
                return p
        return None


# ══════════════════════════════════════════════════════════
# GameManager — handles multiple simultaneous games
# ══════════════════════════════════════════════════════════

class GameManager:
    def __init__(self):
        self._games: dict[int, Game] = {}  # chat_id → Game

    def create_game(self, chat_id: int) -> Game:
        game = Game(chat_id)
        self._games[chat_id] = game
        return game

    def get_game(self, chat_id: int) -> Optional[Game]:
        return self._games.get(chat_id)

    def remove_game(self, chat_id: int) -> bool:
        if chat_id in self._games:
            del self._games[chat_id]
            return True
        return False

    def all_games(self) -> list[Game]:
        return list(self._games.values())
