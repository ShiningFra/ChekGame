#!/usr/bin/env python3
"""
CheckGame Bot — compatible python-telegram-bot >= 21.x (testé v22.7)

Setup:
    pip install "python-telegram-bot>=21,<23"

Lancement:
    BOT_TOKEN="..." python bot.py
"""

import os
import json
import logging
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InlineQueryResultPhoto,
    InputTextMessageContent,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChosenInlineResultHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
)

from game import Card, Game, GameManager
from card_images import card_to_image_number

# ──────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "VOTRE_TOKEN_ICI")

# Chargement des file_id images (généré par upload_cards.py)
_file_id_cache: dict[int, str] = {}
_FILE_IDS_PATH = os.environ.get("FILE_IDS_PATH", "file_ids.json")
if os.path.exists(_FILE_IDS_PATH):
    with open(_FILE_IDS_PATH, encoding="utf-8") as _f:
        _file_id_cache = {int(k): v for k, v in json.load(_f).items()}
    logger.info("✅ %d file_ids chargés depuis %s", len(_file_id_cache), _FILE_IDS_PATH)

IMAGES_BASE_URL = os.environ.get("IMAGES_BASE_URL", "")

gm = GameManager()


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

def _image_url(card: Card) -> Optional[str]:
    if not IMAGES_BASE_URL:
        return None
    return f"{IMAGES_BASE_URL.rstrip('/')}/{card_to_image_number(card)}.jpg"


def _card_label(card: Card) -> str:
    v = {"J": "J", "Q": "Q", "K": "K", "A": "A", "JOKER": "🃏"}.get(card.value, card.value)
    return f"{v}{card.suit_emoji()}"


def _status_text(game: Game) -> str:
    current = game.current_player()
    lines = [
        "🃏 <b>CheckGame en cours !</b>",
        "",
        f"🎴 Carte du dessus : <b>{game.top_card}</b>",
    ]
    if game.under_attack:
        lines.append(f"⚔️ <b>Attaque en cours : {game.attack_stack} carte(s) à piocher !</b>")
    lines += ["", "👥 <b>Joueurs :</b>"]
    for i, p in enumerate(game.players):
        arrow = "▶️" if i == game.turn_index else "　"
        check = " 🔔<i>CHECK!</i>" if len(p.hand) == 1 else ""
        lines.append(f"{arrow} {p.name} — {len(p.hand)} carte(s){check}")
    lines += [
        "",
        f"C'est au tour de <b>{current.name}</b> — {current.mention()} à toi !",
        "Utilise le bouton ci-dessous pour jouer.",
    ]
    return "\n".join(lines)


def _game_keyboard(chat_id: int, game: Game) -> InlineKeyboardMarkup:
    """Clavier normal ou clavier sous attaque selon l'état."""
    if game.under_attack:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🃏 Counter !",
                switch_inline_query_current_chat=f"play_{chat_id}",
            ),
            InlineKeyboardButton(
                f"💀 Subir ({game.attack_stack} cartes)",
                callback_data=f"suffer_{chat_id}",
            ),
        ]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🃏 Jouer une carte",
            switch_inline_query_current_chat=f"play_{chat_id}",
        ),
        InlineKeyboardButton("📥 Piocher", callback_data=f"draw_{chat_id}"),
    ]])


def _draw_or_pass_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🃏 Jouer la carte piochée",
            switch_inline_query_current_chat=f"play_{chat_id}",
        ),
        InlineKeyboardButton("⏭️ Passer", callback_data=f"pass_{chat_id}"),
    ]])


def _suit_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("♠️ Pique",   callback_data=f"suit_{chat_id}_spades"),
            InlineKeyboardButton("♥️ Cœur",    callback_data=f"suit_{chat_id}_hearts"),
        ],
        [
            InlineKeyboardButton("♦️ Carreau", callback_data=f"suit_{chat_id}_diamonds"),
            InlineKeyboardButton("♣️ Trèfle",  callback_data=f"suit_{chat_id}_clubs"),
        ],
    ])


# ══════════════════════════════════════════════════════════
# COMMANDES
# ══════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "♠️♥️♦️♣️ <b>Bienvenue sur CheckGame Bot !</b> ♠️♥️♦️♣️\n\n"
        "Le <b>CheckGame</b> est un jeu de cartes inspiré du UNO, "
        "qui se joue avec un jeu de 54 cartes standard.\n"
        "Chaque joueur reçoit <b>5 cartes</b> et doit s'en débarrasser "
        "avant les autres en posant des cartes compatibles.\n\n"
        "🎯 <b>Objectif :</b> être le premier à n'avoir plus aucune carte en main.\n"
        "🔔 Quand il t'en reste une seule, crie <b>CHECK !</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>Pour jouer :</b>\n"
        "Ajoute ce bot dans un groupe Telegram et tape /newgame.\n"
        "Les cartes se jouent via le bouton inline — discret, propre, sans spam.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📖 /help — Règles complètes\n"
        "🎲 /newgame — Lancer une partie\n",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 <b>Règles du CheckGame</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🃏 <b>Comment jouer une carte ?</b>\n"
        "Une carte est jouable si elle a le <b>même chiffre</b> "
        "ou la <b>même couleur (symbole)</b> que la carte du dessus.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Cartes spéciales :</b>\n\n"
        "🔵 <b>Valet (J)</b> — Carte joker de couleur\n"
        "   ↳ Jouable sur n'importe quelle carte.\n"
        "   ↳ Tu choisis la couleur suivante.\n\n"
        "🔴 <b>7</b> — Carte d'attaque\n"
        "   ↳ Le joueur suivant pioche <b>2 cartes</b> et passe son tour.\n\n"
        "🟡 <b>As (A)</b> — Carte pause\n"
        "   ↳ Le joueur suivant <b>passe son tour</b>.\n\n"
        "👻 <b>2</b> — Carte fantôme\n"
        "   ↳ Jouable sur <b>n'importe quelle carte</b>.\n"
        "   ↳ Se place en dessous : la carte du dessus <b>reste inchangée</b>.\n\n"
        "🌈 <b>Joker</b> — Carte suprême\n"
        "   ↳ Jouable sur n'importe quelle carte.\n"
        "   ↳ Tu choisis la couleur suivante.\n"
        "   ↳ Le joueur suivant pioche <b>4 cartes</b>.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>Victoire :</b> premier à 0 carte en main.\n"
        "🔔 <b>CHECK !</b> : annonce-le quand il te reste 1 seule carte.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎲 /newgame — Lancer une partie\n"
        "🛑 /stop — Annuler la partie en cours",
        parse_mode=ParseMode.HTML,
    )


async def cmd_newgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if gm.get_game(chat_id):
        await update.message.reply_text(
            "⚠️ Une partie est déjà en cours ici.\n"
            "Utilise /stop pour l'annuler d'abord."
        )
        return
    gm.create_game(chat_id)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✋ Rejoindre", callback_data=f"join_{chat_id}"),
        InlineKeyboardButton("▶️ Lancer",   callback_data=f"start_{chat_id}"),
    ]])
    await update.message.reply_text(
        "🎲 <b>Nouvelle partie de CheckGame !</b>\n\n"
        "Clique <b>Rejoindre</b> pour participer.\n"
        "L'hôte clique <b>Lancer</b> quand tout le monde est prêt.\n"
        "<i>(Minimum 2 joueurs)</i>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if gm.remove_game(chat_id):
        await update.message.reply_text("🛑 Partie annulée.")
    else:
        await update.message.reply_text("Aucune partie en cours dans ce groupe.")


# ══════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data: str = query.data
    user = query.from_user

    if data == "noop":
        return

    if data.startswith("join_"):
        chat_id = int(data.removeprefix("join_"))
        game = gm.get_game(chat_id)
        if not game:
            await query.answer("La partie n'existe plus.", show_alert=True)
            return
        if game.started:
            await query.answer("La partie a déjà commencé !", show_alert=True)
            return
        if not game.add_player(user.id, user.first_name, user.username):
            await query.answer("Tu es déjà inscrit !", show_alert=True)
            return
        names = ", ".join(p.name for p in game.players)
        await query.edit_message_text(
            f"🎲 <b>Salon CheckGame</b>\n\n"
            f"👥 Joueurs ({len(game.players)}) : {names}\n\n"
            f"En attente du lancement…",
            reply_markup=query.message.reply_markup,
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("start_"):
        chat_id = int(data.removeprefix("start_"))
        game = gm.get_game(chat_id)
        if not game:
            return
        if len(game.players) < 2:
            await query.answer("Il faut au moins 2 joueurs !", show_alert=True)
            return
        game.start()
        await query.edit_message_text(
            _status_text(game),
            reply_markup=_game_keyboard(chat_id, game),
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("draw_"):
        chat_id = int(data.removeprefix("draw_"))
        game = gm.get_game(chat_id)
        if not game or not game.started:
            return
        if user.id != game.current_player().user_id:
            await query.answer("Ce n'est pas ton tour !", show_alert=True)
            return

        drawn = game.draw_cards(user.id, 1)
        if not drawn:
            await query.answer("La pioche est vide !", show_alert=True)
            return

        card = drawn[0]
        v = {"J": "J", "Q": "Q", "K": "K", "A": "A", "JOKER": "🃏"}.get(card.value, card.value)
        e = card.suit_emoji()

        if game.can_play(card, user.id):
            # Révèle la carte UNIQUEMENT au joueur via popup (visible que par lui)
            await query.answer(f"Tu as pioché : {v} {e} — elle est jouable !", show_alert=True)
            await query.edit_message_text(
                _status_text(game) + f"\n\n📥 <b>{user.first_name}</b> pioche une carte — elle est jouable !",
                reply_markup=_draw_or_pass_keyboard(chat_id),
                parse_mode=ParseMode.HTML,
            )
        else:
            # Pas jouable → passe le tour, carte non révélée
            await query.answer(f"Tu as pioché : {v} {e} — non jouable, tour passé.", show_alert=True)
            game.next_turn()
            await query.edit_message_text(
                _status_text(game) + f"\n\n📥 <b>{user.first_name}</b> pioche et passe son tour.",
                reply_markup=_game_keyboard(chat_id, game),
                parse_mode=ParseMode.HTML,
            )

    elif data.startswith("pass_"):
        chat_id = int(data.removeprefix("pass_"))
        game = gm.get_game(chat_id)
        if not game or not game.started:
            return
        if user.id != game.current_player().user_id:
            await query.answer("Ce n'est pas ton tour !", show_alert=True)
            return
        game.next_turn()
        await query.edit_message_text(
            _status_text(game) + f"\n\n⏭️ <b>{user.first_name}</b> passe son tour.",
            reply_markup=_game_keyboard(chat_id, game),
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("suffer_"):
        chat_id = int(data.removeprefix("suffer_"))
        game = gm.get_game(chat_id)
        if not game or not game.started:
            return
        if user.id != game.current_player().user_id:
            await query.answer("Ce n'est pas ton tour !", show_alert=True)
            return
        count = game.suffer_attack(user.id)
        await query.edit_message_text(
            _status_text(game) + f"\n\n💀 <b>{user.first_name}</b> subit l'attaque et pioche <b>{count} cartes</b> !",
            reply_markup=_game_keyboard(chat_id, game),
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("suit_"):
        _, chat_id_s, suit = data.split("_", 2)
        chat_id = int(chat_id_s)
        game = gm.get_game(chat_id)
        if not game:
            return
        if user.id != game.pending_suit_chooser:
            await query.answer("Ce n'est pas à toi de choisir !", show_alert=True)
            return
        game.set_top_suit(suit)
        await query.edit_message_text(
            _status_text(game),
            reply_markup=_game_keyboard(chat_id, game),
            parse_mode=ParseMode.HTML,
        )


# ══════════════════════════════════════════════════════════
# INLINE QUERY
# ══════════════════════════════════════════════════════════

async def on_inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query
    text = query.query.strip()

    if not text.startswith("play_"):
        await query.answer(
            [],
            switch_pm_text="Lance /newgame dans un groupe d'abord !",
            switch_pm_parameter="help",
            cache_time=0,
        )
        return

    try:
        chat_id = int(text.removeprefix("play_"))
    except ValueError:
        await query.answer([], cache_time=0)
        return

    game = gm.get_game(chat_id)
    if not game or not game.started:
        await query.answer(
            [InlineQueryResultArticle(
                id="no_game",
                title="Aucune partie en cours",
                input_message_content=InputTextMessageContent("❌ Aucune partie active."),
            )],
            cache_time=0,
        )
        return

    player = game.get_player(query.from_user.id)
    if not player:
        await query.answer(
            [InlineQueryResultArticle(
                id="not_in",
                title="Tu n'es pas dans cette partie",
                input_message_content=InputTextMessageContent("❌ Tu n'es pas dans cette partie."),
            )],
            cache_time=0,
        )
        return

    # On attend un choix de couleur → plus personne ne peut jouer, on l'affiche
    if game.waiting_suit:
        chooser = game.get_player(game.pending_suit_chooser)
        chooser_name = chooser.name if chooser else "?"
        await query.answer(
            [InlineQueryResultArticle(
                id="waiting_suit",
                title=f"⏳ En attente du choix de couleur de {chooser_name}…",
                description="Impossible de jouer pour l'instant",
                input_message_content=InputTextMessageContent(
                    f"⏳ En attente du choix de couleur de <b>{chooser_name}</b>…",
                    parse_mode=ParseMode.HTML,
                ),
            )],
            cache_time=0,
        )
        return

    # Pas ton tour → affiche le statut du jeu (visible seulement par toi, pas dans le groupe)
    is_my_turn = game.current_player().user_id == query.from_user.id
    if not is_my_turn:
        current_name = game.current_player().name
        await query.answer(
            [InlineQueryResultArticle(
                id="not_turn",
                title=f"⏳ C'est le tour de {current_name}",
                description=f"Tu as {len(player.hand)} carte(s) en main. Patiente !",
                input_message_content=InputTextMessageContent(
                    _status_text(game), parse_mode=ParseMode.HTML
                ),
            )],
            cache_time=0,
        )
        return

    results = []
    for card in player.hand:
        playable  = game.can_play(card, player.user_id)
        result_id = f"{chat_id}_{card.to_id()}"
        label = _card_label(card)

        if game.under_attack and not game.can_play(card, player.user_id):
            title = f"🚫 {label}"
            desc  = "Ne peut pas counter"
        elif playable:
            title = f"✅ {label}"
            desc  = "Counter !" if game.under_attack else "Jouer"
        else:
            title = f"🚫 {label}"
            desc  = "Non jouable"

        results.append(InlineQueryResultArticle(
            id=result_id,
            title=title,
            description=desc,
            input_message_content=InputTextMessageContent(
                f"🃏 <b>{query.from_user.first_name}</b> joue <b>{label}</b>",
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⏳ Traitement…", callback_data="noop")
            ]]) if playable else None,
        ))

    # Piocher — masqué si sous attaque (doit utiliser le bouton "Subir" dans le groupe)
    if not game.under_attack:
        results.append(InlineQueryResultArticle(
            id=f"{chat_id}_draw",
            title="📥 Piocher",
            description="Tirer une carte de la pioche",
            input_message_content=InputTextMessageContent(
                f"📥 <b>{query.from_user.first_name}</b> pioche une carte.",
                parse_mode=ParseMode.HTML,
            ),
        ))

    await query.answer(results, cache_time=0)


async def _try_dm(bot, user_id: int, text: str) -> None:
    """Tente d'envoyer un DM. Ignore silencieusement si le user n'a pas démarré le bot."""
    try:
        await bot.send_message(user_id, text)
    except Exception:
        pass  # Forbidden: user never started the bot — on ignore


# ══════════════════════════════════════════════════════════
# CHOSEN INLINE RESULT
# ══════════════════════════════════════════════════════════

async def _send_game_state(bot, chat_id: int, game: Game, effect_msg: str = "") -> None:
    """Envoie le statut de jeu avec le bouton d'action."""
    text = _status_text(game)
    if effect_msg:
        text += f"\n\n{effect_msg}"
    await bot.send_message(
        chat_id, text,
        reply_markup=_game_keyboard(chat_id, game),
        parse_mode=ParseMode.HTML,
    )


async def _send_card_played(bot, chat_id: int, user_first_name: str, card: Card, caption_extra: str = "") -> None:
    """
    Envoie l'image de la carte jouée dans le groupe.
    Fallback texte si pas de file_id disponible.
    """
    img_num = card_to_image_number(card)
    v = {"J": "J", "Q": "Q", "K": "K", "A": "A", "JOKER": "🃏"}.get(card.value, card.value)
    e = card.suit_emoji()
    caption = f"🃏 <b>{user_first_name}</b> joue <b>{v} {e}</b>"
    if caption_extra:
        caption += f"\n{caption_extra}"

    if img_num in _file_id_cache:
        await bot.send_photo(
            chat_id,
            photo=_file_id_cache[img_num],
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    else:
        # Fallback texte simple
        await bot.send_message(chat_id, caption, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════
# CHOSEN INLINE RESULT
# ══════════════════════════════════════════════════════════

async def on_chosen_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    result  = update.chosen_inline_result
    user    = result.from_user
    rid     = result.result_id

    first_sep = rid.index("_")
    chat_id   = int(rid[:first_sep])
    card_id   = rid[first_sep + 1:]

    game = gm.get_game(chat_id)
    if not game or not game.started:
        return

    # ── Guard : choix de couleur en attente → bloquer ──
    if game.waiting_suit:
        # Quelqu'un a joué J ou Joker, on attend le choix de couleur
        # Rien d'autre ne peut être joué
        return

    # ── Pas le bon joueur ──
    if user.id != game.current_player().user_id:
        await ctx.bot.send_message(
            chat_id,
            f"⏳ Ce n'est pas le tour de <b>{user.first_name}</b> !",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Piocher (via inline) ──
    if card_id == "draw":
        drawn = game.draw_cards(user.id, 1)
        if not drawn:
            await ctx.bot.send_message(chat_id, "⚠️ La pioche est vide !", parse_mode=ParseMode.HTML)
            return
        card = drawn[0]
        v = {"J": "J", "Q": "Q", "K": "K", "A": "A", "JOKER": "🃏"}.get(card.value, card.value)
        e = card.suit_emoji()
        if game.can_play(card, user.id):
            # Carte jouable : ne révèle pas la carte dans le groupe
            await ctx.bot.send_message(
                chat_id,
                _status_text(game) + f"\n\n📥 <b>{user.first_name}</b> pioche une carte — elle est jouable !",
                reply_markup=_draw_or_pass_keyboard(chat_id),
                parse_mode=ParseMode.HTML,
            )
        else:
            game.next_turn()
            await ctx.bot.send_message(
                chat_id,
                _status_text(game) + f"\n\n📥 <b>{user.first_name}</b> pioche et passe son tour.",
                reply_markup=_game_keyboard(chat_id, game),
                parse_mode=ParseMode.HTML,
            )
        return

    # ── Jouer une carte ──
    card = Card.from_id(card_id)
    if not game.can_play(card, user.id):
        # Carte invalide : on avertit sans nommer la carte
        await ctx.bot.send_message(
            chat_id,
            f"⚠️ <b>{user.first_name}</b> a tenté de jouer une carte non valide. Tour passé.",
            parse_mode=ParseMode.HTML,
        )
        game.next_turn()
        await _send_game_state(ctx.bot, chat_id, game)
        return

    effect_msg = game.play_card(user.id, card)

    # Victoire ?
    winner = game.check_winner()
    if winner:
        v = {"J": "J", "Q": "Q", "K": "K", "A": "A", "JOKER": "🃏"}.get(card.value, card.value)
        await _send_card_played(ctx.bot, chat_id, user.first_name, card)
        gm.remove_game(chat_id)
        await ctx.bot.send_message(
            chat_id,
            f"🏆 <b>{winner.name} remporte la partie !</b> 🎉",
            parse_mode=ParseMode.HTML,
        )
        return

    # Choix de couleur requis (J ou Joker) ?
    if game.waiting_suit:
        await _send_card_played(ctx.bot, chat_id, user.first_name, card)
        extra = ""
        if game.under_attack:
            extra = f"\n⚔️ Pile d'attaque : <b>{game.attack_stack}</b> carte(s) en jeu."
        await ctx.bot.send_message(
            chat_id,
            f"🎨 <b>{user.first_name}</b>, choisis la couleur :{extra}",
            reply_markup=_suit_keyboard(chat_id),
            parse_mode=ParseMode.HTML,
        )
        return

    # Tour normal : image de la carte puis statut
    await _send_card_played(ctx.bot, chat_id, user.first_name, card,
                            caption_extra=effect_msg if effect_msg else "")
    await _send_game_state(ctx.bot, chat_id, game)


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("newgame", cmd_newgame))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(InlineQueryHandler(on_inline_query))
    app.add_handler(ChosenInlineResultHandler(on_chosen_result))

    import telegram
    logger.info("🃏 CheckGame Bot démarré (python-telegram-bot %s)", telegram.__version__)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
