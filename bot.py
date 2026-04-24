#!/usr/bin/env python3
"""
CheckGame Bot — Telegram inline bot for the CheckGame card game.
Similar to @unobot but for CheckGame rules.

Requirements:
    pip install python-telegram-bot==20.7

Usage:
    Set BOT_TOKEN env variable and run:  python bot.py
"""

import os
import logging
import random
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQueryResultArticle, InputTextMessageContent,
    InlineQueryResultCachedPhoto, InlineQueryResultPhoto,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    InlineQueryHandler, ContextTypes, ChosenInlineResultHandler,
)
from telegram.constants import ParseMode
from game import GameManager, Game, Card, SUITS, SPECIAL_CARDS
from card_images import card_to_image_number

# ──────────────────────────────────────────────────────────
# Cache file_id Telegram pour chaque numéro d'image (1-54)
# Rempli automatiquement au premier envoi de chaque carte.
# ──────────────────────────────────────────────────────────
_file_id_cache: dict[int, str] = {}   # image_number → telegram file_id

# Charge file_ids.json au démarrage (généré par upload_cards.py)
import json as _json
_FILE_IDS_PATH = os.environ.get("FILE_IDS_PATH", "file_ids.json")
if os.path.exists(_FILE_IDS_PATH):
    with open(_FILE_IDS_PATH) as _f:
        _file_id_cache = {int(k): v for k, v in _json.load(_f).items()}

CARDS_CHANNEL_ID = os.environ.get("CARDS_CHANNEL_ID", "")  # optionnel
IMAGES_BASE_URL = os.environ.get(
    "IMAGES_BASE_URL", ""
)  # ex: "https://monsite.com/cards/"  (doit se terminer par /)

def card_image_url(card: Card) -> str | None:
    """Retourne l'URL publique de l'image si IMAGES_BASE_URL est défini."""
    if not IMAGES_BASE_URL:
        return None
    return f"{IMAGES_BASE_URL}{card_to_image_number(card)}.jpg"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Global game manager (handles multiple simultaneous games)
# ──────────────────────────────────────────────────────────
gm = GameManager()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "VOTRE_TOKEN_ICI")


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

def game_status_text(game: Game) -> str:
    """Build the status message shown in the group."""
    current = game.current_player()
    lines = [
        f"🃏 <b>CheckGame en cours !</b>",
        f"",
        f"🎴 Carte du dessus : <b>{game.top_card}</b>",
        f"",
        f"👥 <b>Joueurs :</b>",
    ]
    for i, p in enumerate(game.players):
        arrow = "▶️" if i == game.turn_index else "  "
        check = " 🔔<i>CHECK!</i>" if len(p.hand) == 1 else ""
        lines.append(f"{arrow} {p.name} — {len(p.hand)} carte(s){check}")
    lines += [
        f"",
        f"C'est au tour de <b>{current.name}</b> de jouer !",
        f"Utilise le bouton ci-dessous pour jouer tes cartes.",
    ]
    return "\n".join(lines)


def play_button(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🃏 Jouer une carte",
            switch_inline_query_current_chat=f"play_{game_id}"
        )
    ]])


def draw_button(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🃏 Jouer une carte", switch_inline_query_current_chat=f"play_{game_id}"),
        InlineKeyboardButton("📥 Piocher", callback_data=f"draw_{game_id}"),
    ]])


# ══════════════════════════════════════════════════════════
# /newgame  — start a game in the group
# ══════════════════════════════════════════════════════════

async def new_game(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if gm.get_game(chat_id):
        await update.message.reply_text(
            "⚠️ Une partie est déjà en cours dans ce groupe.\n"
            "Termine-la avant d'en commencer une nouvelle."
        )
        return
    game = gm.create_game(chat_id)
    ctx.chat_data["game_id"] = chat_id
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✋ Rejoindre", callback_data=f"join_{chat_id}"),
        InlineKeyboardButton("▶️ Lancer la partie", callback_data=f"start_{chat_id}"),
    ]])
    msg = await update.message.reply_text(
        "🎲 <b>Nouvelle partie de CheckGame !</b>\n\n"
        "Clique sur <b>Rejoindre</b> pour participer.\n"
        "Le créateur clique sur <b>Lancer</b> quand tout le monde est prêt.\n"
        "(Minimum 2 joueurs)",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )
    game.lobby_message_id = msg.message_id


# ══════════════════════════════════════════════════════════
# Callback: join / start
# ══════════════════════════════════════════════════════════

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    # ── JOIN ──
    if data.startswith("join_"):
        chat_id = int(data.split("_")[1])
        game = gm.get_game(chat_id)
        if not game:
            await query.answer("La partie n'existe plus.", show_alert=True)
            return
        if game.started:
            await query.answer("La partie a déjà commencé !", show_alert=True)
            return
        if game.add_player(user.id, user.first_name):
            names = ", ".join(p.name for p in game.players)
            await query.edit_message_text(
                f"🎲 <b>Salon CheckGame</b>\n\n"
                f"👥 Joueurs ({len(game.players)}) : {names}\n\n"
                f"En attente du lancement…",
                reply_markup=query.message.reply_markup,
                parse_mode=ParseMode.HTML,
            )
        else:
            await query.answer("Tu es déjà dans la partie !", show_alert=True)

    # ── START ──
    elif data.startswith("start_"):
        chat_id = int(data.split("_")[1])
        game = gm.get_game(chat_id)
        if not game:
            return
        if len(game.players) < 2:
            await query.answer("Il faut au moins 2 joueurs !", show_alert=True)
            return
        game.start()
        await query.edit_message_text(
            game_status_text(game),
            reply_markup=draw_button(chat_id),
            parse_mode=ParseMode.HTML,
        )

    # ── DRAW (piocher) ──
    elif data.startswith("draw_"):
        chat_id = int(data.split("_")[1])
        game = gm.get_game(chat_id)
        if not game or not game.started:
            return
        current = game.current_player()
        if user.id != current.user_id:
            await query.answer("Ce n'est pas ton tour !", show_alert=True)
            return
        drawn = game.draw_cards(user.id, 1)
        card_str = str(drawn[0]) if drawn else "rien"
        await query.answer(f"Tu as pioché : {card_str}", show_alert=True)
        # After drawing, player must pass turn
        game.next_turn()
        await query.edit_message_text(
            game_status_text(game),
            reply_markup=draw_button(chat_id),
            parse_mode=ParseMode.HTML,
        )

    # ── CHOOSE SUIT (after J or Joker) ──
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
        game.pending_suit_chooser = None
        # Now advance turn
        game.next_turn()
        await query.edit_message_text(
            game_status_text(game),
            reply_markup=draw_button(chat_id),
            parse_mode=ParseMode.HTML,
        )

    # ── STOP GAME ──
    elif data.startswith("stop_"):
        chat_id = int(data.split("_")[1])
        gm.remove_game(chat_id)
        await query.edit_message_text("🛑 Partie annulée.")


# ══════════════════════════════════════════════════════════
# Inline query — player selects a card to play
# ══════════════════════════════════════════════════════════

async def inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    text = query.query.strip()

    if not text.startswith("play_"):
        await query.answer([], switch_pm_text="Lance /newgame dans un groupe !", switch_pm_parameter="help")
        return

    try:
        chat_id = int(text.split("_")[1])
    except (IndexError, ValueError):
        await query.answer([])
        return

    game = gm.get_game(chat_id)
    if not game or not game.started:
        await query.answer(
            [InlineQueryResultArticle(
                id="no_game",
                title="Aucune partie en cours",
                input_message_content=InputTextMessageContent("❌ Aucune partie active."),
            )]
        )
        return

    player = game.get_player(query.from_user.id)
    if not player:
        await query.answer(
            [InlineQueryResultArticle(
                id="not_in_game",
                title="Tu n'es pas dans cette partie",
                input_message_content=InputTextMessageContent("❌ Tu n'es pas dans cette partie."),
            )]
        )
        return

    results = []
    for card in player.hand:
        playable = game.can_play(card, player.user_id)
        status = "✅" if playable else "🚫"
        emoji = card.suit_emoji()
        img_num = card_to_image_number(card)
        result_id = f"{chat_id}_{card.to_id()}"
        caption = f"🃏 {query.from_user.first_name} joue <b>{card}</b> {emoji}"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("⏳ Application en cours…", callback_data="noop")
        ]]) if playable else None

        # ── Cas 1 : on a déjà le file_id Telegram en cache ──
        if img_num in _file_id_cache:
            results.append(
                InlineQueryResultCachedPhoto(
                    id=result_id,
                    photo_file_id=_file_id_cache[img_num],
                    title=f"{status} {card}",
                    description="Jouer cette carte" if playable else "Non jouable",
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            )
        # ── Cas 2 : URL publique disponible (IMAGES_BASE_URL défini) ──
        elif card_image_url(card):
            url = card_image_url(card)
            results.append(
                InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=url,
                    thumbnail_url=url,
                    title=f"{status} {card}",
                    description="Jouer cette carte" if playable else "Non jouable",
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            )
        # ── Cas 3 : fallback texte ──
        else:
            results.append(
                InlineQueryResultArticle(
                    id=result_id,
                    title=f"{status} {card}",
                    description="Jouer cette carte" if playable else "Non jouable",
                    input_message_content=InputTextMessageContent(
                        caption, parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=kb,
                )
            )

    # Option piocher
    results.append(
        InlineQueryResultArticle(
            id=f"{chat_id}_draw",
            title="📥 Piocher une carte",
            description="Passer en piochant",
            input_message_content=InputTextMessageContent(
                f"📥 {query.from_user.first_name} pioche une carte.",
                parse_mode=ParseMode.HTML,
            ),
        )
    )

    await query.answer(results, cache_time=0)


# ══════════════════════════════════════════════════════════
# Chosen inline result — actually apply the card play
# ══════════════════════════════════════════════════════════

async def chosen_inline_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    result = update.chosen_inline_result
    result_id = result.result_id
    user = result.from_user

    parts = result_id.split("_")
    if len(parts) < 2:
        return

    chat_id = int(parts[0])
    card_id = "_".join(parts[1:])

    game = gm.get_game(chat_id)
    if not game or not game.started:
        return

    current = game.current_player()
    if user.id != current.user_id:
        # Not your turn, ignore
        await ctx.bot.send_message(
            user.id,
            "❌ Ce n'était pas ton tour ! La carte n'a pas été jouée.",
        )
        return

    if card_id == "draw":
        drawn = game.draw_cards(user.id, 1)
        game.next_turn()
        status = game_status_text(game)
        await ctx.bot.send_message(
            chat_id,
            status,
            reply_markup=draw_button(chat_id),
            parse_mode=ParseMode.HTML,
        )
        return

    card = Card.from_id(card_id)
    if not game.can_play(card, user.id):
        await ctx.bot.send_message(
            user.id,
            f"❌ Tu ne peux pas jouer {card} maintenant !",
        )
        return

    effect_msg = game.play_card(user.id, card)

    # Check win
    winner = game.check_winner()
    if winner:
        gm.remove_game(chat_id)
        await ctx.bot.send_message(
            chat_id,
            f"🏆 <b>{winner.name} a gagné la partie de CheckGame !</b>\n\n"
            f"Félicitations ! 🎉",
            parse_mode=ParseMode.HTML,
        )
        return

    # Handle suit choice (J or Joker)
    if game.pending_suit_chooser:
        suit_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("♠️ Pique", callback_data=f"suit_{chat_id}_spades"),
            InlineKeyboardButton("♥️ Cœur", callback_data=f"suit_{chat_id}_hearts"),
        ], [
            InlineKeyboardButton("♦️ Carreau", callback_data=f"suit_{chat_id}_diamonds"),
            InlineKeyboardButton("♣️ Trèfle", callback_data=f"suit_{chat_id}_clubs"),
        ]])
        await ctx.bot.send_message(
            chat_id,
            f"🃏 <b>{user.first_name}</b> joue un <b>{card}</b> !\n"
            f"Choisis la couleur :",
            reply_markup=suit_kb,
            parse_mode=ParseMode.HTML,
        )
        return

    status = game_status_text(game)
    extra = f"\n\n{effect_msg}" if effect_msg else ""
    await ctx.bot.send_message(
        chat_id,
        status + extra,
        reply_markup=draw_button(chat_id),
        parse_mode=ParseMode.HTML,
    )


# ══════════════════════════════════════════════════════════
# /stop — cancel current game
# ══════════════════════════════════════════════════════════

async def stop_game(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if gm.remove_game(chat_id):
        await update.message.reply_text("🛑 Partie annulée.")
    else:
        await update.message.reply_text("Aucune partie en cours dans ce groupe.")


# ══════════════════════════════════════════════════════════
# /help
# ══════════════════════════════════════════════════════════

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🃏 <b>CheckGame Bot</b>\n\n"
        "<b>Commandes :</b>\n"
        "/newgame — Démarrer une partie\n"
        "/stop — Annuler la partie en cours\n"
        "/help — Afficher ce message\n\n"
        "<b>Règles rapides :</b>\n"
        "• Joue une carte de même chiffre ou même couleur\n"
        "• <b>J</b> = changer la couleur\n"
        "• <b>7</b> = le suivant pioche 2 cartes\n"
        "• <b>As</b> = le suivant passe son tour\n"
        "• <b>2</b> = carte fantôme (se joue toujours, la top card ne change pas)\n"
        "• <b>Joker</b> = changer couleur + le suivant pioche 4 cartes\n"
        "• Crie <b>CHECK !</b> quand il te reste 1 carte\n"
        "• Premier à 0 carte = victoire 🏆",
        parse_mode=ParseMode.HTML,
    )


# ══════════════════════════════════════════════════════════
# noop callback (placeholder button)
# ══════════════════════════════════════════════════════════

async def noop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("newgame", new_game))
    app.add_handler(CommandHandler("stop", stop_game))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("start", help_cmd))

    app.add_handler(CallbackQueryHandler(noop, pattern="^noop$"))
    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(ChosenInlineResultHandler(chosen_inline_result))

    logger.info("CheckGame Bot démarré !")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
