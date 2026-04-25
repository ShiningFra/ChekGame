"""
game.py — CheckGame core logic (v2, bugs fixed)

Corrections:
- pending_suit_chooser correctement remis à None après choix
- Aucune carte jouable pendant qu'on attend le choix de couleur
- Counter 7/Joker correctement géré (stack accumulé)
- Joker en counter : choix de couleur requis avant d'avancer le tour
"""

import random
from dataclasses import dataclass, field
from typing import Optional

SUITS = ["spades", "hearts", "diamonds", "clubs"]
SUIT_EMOJI = {"spades": "♠️", "hearts": "♥️", "diamonds": "♦️", "clubs": "♣️", "joker": "🃏"}
VALUES = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SPECIAL_CARDS = {"J", "7", "A", "2", "JOKER"}
VALUE_DISPLAY = {"J": "J", "Q": "Q", "K": "K", "A": "A", "JOKER": "Joker"}


@dataclass(frozen=True)
class Card:
    value: str
    suit: str

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
        return self.value == "2"

    @property
    def is_wild(self) -> bool:
        return self.value in ("J", "JOKER")

    @property
    def draw_count(self) -> int:
        if self.value == "7":
            return 2
        if self.value == "JOKER":
            return 4
        return 0


def build_deck() -> list[Card]:
    deck = []
    for suit in SUITS:
        for value in VALUES:
            deck.append(Card(value=value, suit=suit))
    deck.append(Card(value="JOKER", suit="joker"))
    deck.append(Card(value="JOKER", suit="joker"))
    random.shuffle(deck)
    return deck


@dataclass
class Player:
    user_id: int
    name: str
    username: Optional[str] = None
    hand: list[Card] = field(default_factory=list)

    def mention(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.name

    def remove_card(self, card: Card):
        self.hand.remove(card)

    def add_cards(self, cards: list[Card]):
        self.hand.extend(cards)


class Game:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.players: list[Player] = []
        self.started = False
        self.deck: list[Card] = []
        self.discard: list[Card] = []
        self.turn_index: int = 0
        self.direction: int = 1

        # Choix de couleur en attente (J ou Joker joué)
        # Tant que != None, PERSONNE ne peut jouer de carte — on attend le choix
        self.pending_suit_chooser: Optional[int] = None  # user_id

        self._current_suit: Optional[str] = None

        # Chaîne d'attaque (7 et Joker stackables)
        self.attack_stack: int = 0
        self.attack_type: Optional[str] = None

    # ── Setup ──────────────────────────────────────────────

    def add_player(self, user_id: int, name: str, username: Optional[str] = None) -> bool:
        if any(p.user_id == user_id for p in self.players):
            return False
        self.players.append(Player(user_id=user_id, name=name, username=username))
        return True

    def get_player(self, user_id: int) -> Optional[Player]:
        return next((p for p in self.players if p.user_id == user_id), None)

    def start(self):
        self.deck = build_deck()
        random.shuffle(self.players)
        for player in self.players:
            player.hand = [self.deck.pop() for _ in range(5)]
        # Première carte : ni spéciale ni attaque
        while True:
            card = self.deck.pop()
            if card.value not in ("J", "JOKER", "2", "7", "A"):
                self.discard.append(card)
                break
            self.deck.insert(0, card)
        self.started = True

    # ── State ──────────────────────────────────────────────

    @property
    def top_card(self) -> Card:
        return self.discard[-1]

    @property
    def effective_suit(self) -> str:
        if self._current_suit:
            return self._current_suit
        return self.top_card.suit

    def current_player(self) -> Player:
        return self.players[self.turn_index]

    @property
    def under_attack(self) -> bool:
        return self.attack_stack > 0

    @property
    def waiting_suit(self) -> bool:
        """True si on attend que quelqu'un choisisse une couleur."""
        return self.pending_suit_chooser is not None

    # ── Playability ────────────────────────────────────────

    def can_play(self, card: Card, user_id: int) -> bool:
        # Pas son tour
        if self.current_player().user_id != user_id:
            return False

        # On attend un choix de couleur → PERSONNE ne joue, même le joueur courant
        if self.waiting_suit:
            return False

        # Sous attaque : seul un counter (7 ou Joker) est autorisé
        if self.under_attack:
            return card.value in ("7", "JOKER")

        # Règles normales
        if card.is_phantom:   # 2 : toujours jouable
            return True
        if card.is_wild:      # J ou Joker : toujours jouable
            return True
        suit_match  = card.suit  == self.effective_suit
        value_match = card.value == self.top_card.value
        return suit_match or value_match

    def has_counter(self, user_id: int) -> bool:
        player = self.get_player(user_id)
        if not player:
            return False
        return any(c.value in ("7", "JOKER") for c in player.hand)

    # ── Play a card ────────────────────────────────────────

    def play_card(self, user_id: int, card: Card) -> str:
        """
        Applique l'effet de la carte.
        Retourne un message d'effet (peut être vide).
        NE PAS appeler si can_play() retourne False.
        """
        player = self.get_player(user_id)
        player.remove_card(card)

        # ── Carte fantôme (2) ──────────────────────────────
        if card.is_phantom:
            # Glisse sous la top card, celle-ci reste active
            if len(self.discard) >= 1:
                self.discard.insert(len(self.discard) - 1, card)
            else:
                self.discard.append(card)
            self.next_turn()
            return "👻 Carte fantôme ! La carte du dessus reste inchangée."

        # Pose normale
        self.discard.append(card)
        self._current_suit = None  # reset override de couleur

        # ── 7 : attaque +2 ────────────────────────────────
        if card.value == "7":
            self.attack_stack += 2
            self.attack_type = "7"
            self.next_turn()
            return f"⚔️ +2 ! Pile d'attaque : <b>{self.attack_stack}</b> carte(s). Counter ou subir !"

        # ── Joker : attaque +4 + choix couleur ───────────
        elif card.value == "JOKER":
            self.attack_stack += 4
            self.attack_type = "JOKER"
            # Bloque tout le monde pendant le choix de couleur
            # Le tour avancera dans set_top_suit()
            self.pending_suit_chooser = user_id
            return f"🌈 Joker +4 ! Pile d'attaque : <b>{self.attack_stack}</b>. Choix de couleur requis."

        # ── As : skip ─────────────────────────────────────
        elif card.value == "A":
            self._skip_turn()
            return "⏸️ Pause ! Le joueur suivant passe son tour."

        # ── Valet : choix de couleur ──────────────────────
        elif card.value == "J":
            # Bloque tout le monde pendant le choix
            # Le tour avancera dans set_top_suit()
            self.pending_suit_chooser = user_id
            return "🎨 Valet ! Choix de couleur requis."

        # ── Carte normale ──────────────────────────────────
        else:
            self.next_turn()
            return ""

    def set_top_suit(self, suit: str):
        """
        Appelé quand le joueur choisit la couleur après J ou Joker.
        Remet pending_suit_chooser à None et avance le tour.
        """
        self._current_suit = suit
        self.pending_suit_chooser = None   # ← FIX : toujours remettre à None ici

        # Si c'était un Joker counter (attaque en cours), on avance le tour
        # pour que le joueur suivant puisse counter ou subir.
        # Si c'était un J normal, on avance aussi.
        self.next_turn()

    def suffer_attack(self, user_id: int) -> int:
        """Le joueur subit l'attaque : pioche attack_stack cartes, tour passé."""
        count = self.attack_stack
        self.draw_cards(user_id, count)
        self.attack_stack = 0
        self.attack_type  = None
        self.next_turn()
        return count

    # ── Turn management ────────────────────────────────────

    def next_turn(self):
        n = len(self.players)
        self.turn_index = (self.turn_index + self.direction) % n

    def _skip_turn(self):
        n = len(self.players)
        self.turn_index = (self.turn_index + 2 * self.direction) % n

    def _deal(self, count: int) -> list[Card]:
        result = []
        for _ in range(count):
            if not self.deck:
                if len(self.discard) <= 1:
                    break
                top = self.discard.pop()
                self.deck = self.discard[:]
                random.shuffle(self.deck)
                self.discard = [top]
            result.append(self.deck.pop())
        return result

    def draw_cards(self, user_id: int, count: int) -> list[Card]:
        player = self.get_player(user_id)
        drawn  = self._deal(count)
        player.add_cards(drawn)
        return drawn

    def check_winner(self) -> Optional[Player]:
        for p in self.players:
            if len(p.hand) == 0:
                return p
        return None


class GameManager:
    def __init__(self):
        self._games: dict[int, Game] = {}

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
