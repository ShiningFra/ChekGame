# CheckGame Bot 🃏

Bot Telegram pour jouer au **CheckGame** dans n'importe quel groupe,  
inspiré du bot UNO — plusieurs parties simultanées, aucune confusion.

---

## Installation rapide

### 1. Prérequis
- Python 3.11+
- Un token bot Telegram (obtenu via [@BotFather](https://t.me/BotFather))

### 2. Créer le bot sur BotFather
```
/newbot          → donne un nom ex: "CheckGame"
/setinline       → active le mode inline  (OBLIGATOIRE)
/setinlinefeedback → active le feedback inline (OBLIGATOIRE, mets 100%)
```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Lancer le bot
```bash
BOT_TOKEN="123456:ABC-ton-token" python bot.py
```
Ou sur Windows :
```powershell
$env:BOT_TOKEN="123456:ABC-ton-token"
python bot.py
```

---

## Structure du projet

```
checkgame_bot/
├── bot.py          # Handlers Telegram (commandes, callbacks, inline)
├── game.py         # Logique du jeu (deck, joueurs, règles)
├── requirements.txt
└── README.md
```

---

## Comment jouer

1. **Dans un groupe**, tape `/newgame`
2. Les joueurs cliquent **Rejoindre**
3. L'hôte clique **Lancer la partie**
4. Chaque joueur reçoit 5 cartes
5. C'est au tour du 1er joueur : il clique **"Jouer une carte"** → interface inline s'ouvre
6. Il sélectionne une carte jouable (✅) ou pioche (📥)
7. Le jeu continue jusqu'à ce qu'un joueur ait **0 carte** → victoire 🏆

---

## Règles des cartes spéciales

| Carte | Effet |
|-------|-------|
| **Valet (J)** | Peut être joué sur n'importe quelle carte. Permet de choisir la couleur suivante. |
| **7** | Le joueur suivant pioche 2 cartes et passe son tour. |
| **As (A)** | Le joueur suivant passe son tour. |
| **2** | Carte fantôme — jouable sur n'importe quelle carte. Se place sous la top card (la top card reste inchangée). |
| **Joker** | Jouable partout. Choisir la couleur + le joueur suivant pioche 4 cartes. |

---

## Nommage des images de cartes spéciales

| Carte | Fichier |
|-------|---------|
| Valet (J) | `1.jpg` |
| 7 | `2.jpg` |
| As | `3.jpg` |
| 2 | `4.jpg` |
| Joker | `5.jpg` |

Pour utiliser tes images comme `photo_file_id` Telegram, uploade-les d'abord  
via `bot.send_photo()` et stocke les `file_id` retournés dans un dict `CARD_IMAGES`.

---

## Déploiement en production (Render / Railway / VPS)

```bash
# Variable d'environnement à définir :
BOT_TOKEN=ton_token_ici
```

Le bot tourne en mode **polling** par défaut.  
Pour un webhook (recommandé en prod), remplace `run_polling()` par `run_webhook()`.
