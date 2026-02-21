"""
╔══════════════════════════════════════════════════════════════╗
║           PAYS GAME — Client Kivy (Mobile/Desktop)           ║
║                                                              ║
║  Installation :                                              ║
║    pip install kivy websockets                               ║
║                                                              ║
║  Lancement :                                                 ║
║    python main.py                                            ║
║                                                              ║
║  Build Android (Buildozer) :                                 ║
║    buildozer android debug                                   ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import random
import asyncio
import threading
import unicodedata
import uuid
from typing import Optional

import websockets
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import AsyncImage
from kivy.properties import (
    StringProperty, NumericProperty, BooleanProperty,
    ListProperty, ObjectProperty
)
from kivy.clock import Clock, mainthread
from kivy.factory import Factory
from kivy.core.window import Window
from kivy.animation import Animation
from kivy.metrics import dp
from kivy.utils import get_color_from_hex

# Taille simulateur mobile
Window.size = (390, 844)

# ──────────────────────────────────────────────────────────────
#  CONSTANTES
# ──────────────────────────────────────────────────────────────

# ← Changer selon ton hébergement
SERVEUR_WS   = "wss://pays-game.onrender.com"
SERVEUR_HTTP = "https://pays-game.onrender.com"

COULEUR_FOND     = get_color_from_hex("#0d0f14")
COULEUR_OCEAN    = get_color_from_hex("#0a1628")
COULEUR_CARD     = get_color_from_hex("#112240")
COULEUR_TEAL     = get_color_from_hex("#00c9a7")
COULEUR_AMBER    = get_color_from_hex("#f4a947")
COULEUR_CRIMSON  = get_color_from_hex("#e63946")
COULEUR_GOLD     = get_color_from_hex("#d4a853")
COULEUR_PAPIER   = get_color_from_hex("#f5f0e8")
COULEUR_MUTED    = get_color_from_hex("#4a5568")

# ──────────────────────────────────────────────────────────────
#  UTILITAIRES
# ──────────────────────────────────────────────────────────────

def normaliser(s: str) -> str:
    """Supprime accents, espaces et tirets pour la comparaison clavier."""
    s = unicodedata.normalize("NFD", s.upper()).encode("ascii", "ignore").decode("ascii")
    # On ignore espaces et tirets : le joueur ne peut pas les saisir
    return s.replace(" ", "").replace("-", "").replace("'", "")


# ──────────────────────────────────────────────────────────────
#  DÉCLARATION DES ÉCRANS
# ──────────────────────────────────────────────────────────────

class AccueilScreen(Screen):
    pass

class LobbyScreen(Screen):
    pass

class JeuScreen(Screen):
    pass

class FinScreen(Screen):
    pass


# ──────────────────────────────────────────────────────────────
#  KV STRING
# ──────────────────────────────────────────────────────────────

KV = """
#:import get_color_from_hex kivy.utils.get_color_from_hex
#:import Factory kivy.factory.Factory
#:import dp kivy.metrics.dp
#:import SlideTransition kivy.uix.screenmanager.SlideTransition

# ── Widgets réutilisables ───────────────────────────────────

<BtnPrimary@Button>:
    background_normal: ''
    background_color: get_color_from_hex('#00c9a7')
    color: get_color_from_hex('#0d0f14')
    font_name: 'Roboto'
    bold: True
    size_hint_y: None
    height: dp(52)
    font_size: sp(13)

<BtnSecondary@Button>:
    background_normal: ''
    background_color: (1,1,1,0.06)
    color: get_color_from_hex('#f5f0e8')
    font_name: 'Roboto'
    size_hint_y: None
    height: dp(52)
    font_size: sp(13)
    canvas.before:
        Color:
            rgba: 1,1,1,0.1
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, dp(10)
            width: 1

<BtnDanger@Button>:
    background_normal: ''
    background_color: (0.9,0.22,0.27,0.15)
    color: get_color_from_hex('#e63946')
    font_name: 'Roboto'
    size_hint_y: None
    height: dp(48)
    font_size: sp(12)
    canvas.before:
        Color:
            rgba: 0.9,0.22,0.27,0.3
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, dp(10)
            width: 1

<ChampsInput@TextInput>:
    background_color: (1,1,1,0.06)
    foreground_color: get_color_from_hex('#f5f0e8')
    hint_text_color: get_color_from_hex('#4a5568')
    cursor_color: get_color_from_hex('#00c9a7')
    font_name: 'Roboto'
    font_size: sp(15)
    size_hint_y: None
    height: dp(48)
    padding: [dp(14), dp(12), dp(14), dp(12)]
    multiline: False

<LabelTitre@Label>:
    font_name: 'Roboto'
    bold: True
    color: get_color_from_hex('#f5f0e8')

<LabelMono@Label>:
    font_name: 'Roboto'
    color: get_color_from_hex('#4a5568')
    font_size: sp(11)

<ToucheClavier@Button>:
    background_normal: ''
    background_color: (1,1,1,0.06)
    color: get_color_from_hex('#f5f0e8')
    font_name: 'Roboto'
    font_size: sp(13)
    bold: True
    canvas.before:
        Color:
            rgba: 1,1,1,0.08
        Line:
            rounded_rectangle: self.x+1, self.y+1, self.width-2, self.height-2, dp(6)
            width: 1

# ── GESTIONNAIRE D'ÉCRANS ───────────────────────────────────

ScreenManager:
    id: sm
    transition: SlideTransition()
    AccueilScreen:
    LobbyScreen:
    JeuScreen:
    FinScreen:

# ══════════════════════════════════════════════════════════════
#  ÉCRAN 1 — ACCUEIL
# ══════════════════════════════════════════════════════════════

<AccueilScreen>:
    name: 'accueil'
    canvas.before:
        Color:
            rgba: get_color_from_hex('#0a1628')
        Rectangle:
            pos: self.pos
            size: self.size

    ScrollView:
        BoxLayout:
            orientation: 'vertical'
            padding: dp(24)
            spacing: dp(16)
            size_hint_y: None
            height: self.minimum_height

            # Logo
            BoxLayout:
                orientation: 'vertical'
                size_hint_y: None
                height: dp(140)
                spacing: dp(4)
                padding: [0, dp(20), 0, 0]

                Label:
                    text: "🌍"
                    font_size: sp(48)
                    size_hint_y: None
                    height: dp(60)

                Label:
                    text: "PAYS GAME"
                    font_name: 'Roboto'
                    bold: True
                    font_size: sp(32)
                    color: get_color_from_hex('#d4a853')
                    size_hint_y: None
                    height: dp(44)

                Label:
                    text: "LE JEU DES NATIONS"
                    font_name: 'Roboto'
                    font_size: sp(10)
                    letter_spacing: dp(3)
                    color: get_color_from_hex('#00c9a7')
                    size_hint_y: None
                    height: dp(20)

            # Carte formulaire
            BoxLayout:
                orientation: 'vertical'
                spacing: dp(12)
                size_hint_y: None
                height: self.minimum_height
                canvas.before:
                    Color:
                        rgba: get_color_from_hex('#112240')
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(16)]
                padding: dp(20)

                LabelMono:
                    text: "TON NOM"
                    size_hint_y: None
                    height: dp(20)
                    color: get_color_from_hex('#00c9a7')

                ChampsInput:
                    id: input_nom
                    hint_text: "Ex: Alice"

                # Ligne langue + vies
                GridLayout:
                    cols: 2
                    spacing: dp(10)
                    size_hint_y: None
                    height: dp(90)

                    BoxLayout:
                        orientation: 'vertical'
                        spacing: dp(6)
                        LabelMono:
                            text: "LANGUE"
                            color: get_color_from_hex('#00c9a7')
                            size_hint_y: None
                            height: dp(18)
                        Spinner:
                            id: spin_langue
                            values: ['Français 🇫🇷', 'English 🇬🇧']
                            text: 'Français 🇫🇷'
                            background_normal: ''
                            background_color: (1,1,1,0.06)
                            color: get_color_from_hex('#f5f0e8')
                            font_name: 'Roboto'
                            size_hint_y: None
                            height: dp(48)

                    BoxLayout:
                        orientation: 'vertical'
                        spacing: dp(6)
                        LabelMono:
                            text: "VIES"
                            color: get_color_from_hex('#00c9a7')
                            size_hint_y: None
                            height: dp(18)
                        Spinner:
                            id: spin_vies
                            values: ['5 vies', '10 vies', '15 vies']
                            text: '10 vies'
                            background_normal: ''
                            background_color: (1,1,1,0.06)
                            color: get_color_from_hex('#f5f0e8')
                            font_name: 'Roboto'
                            size_hint_y: None
                            height: dp(48)

                # Ligne chrono + mode mixte
                GridLayout:
                    cols: 2
                    spacing: dp(10)
                    size_hint_y: None
                    height: dp(90)

                    BoxLayout:
                        orientation: 'vertical'
                        spacing: dp(6)
                        LabelMono:
                            text: "CHRONO"
                            color: get_color_from_hex('#00c9a7')
                            size_hint_y: None
                            height: dp(18)
                        Spinner:
                            id: spin_temps
                            values: ['10 sec', '15 sec', '30 sec', '60 sec']
                            text: '15 sec'
                            background_normal: ''
                            background_color: (1,1,1,0.06)
                            color: get_color_from_hex('#f5f0e8')
                            font_name: 'Roboto'
                            size_hint_y: None
                            height: dp(48)

                    BoxLayout:
                        orientation: 'vertical'
                        spacing: dp(6)
                        LabelMono:
                            text: "MODE MIXTE"
                            color: get_color_from_hex('#00c9a7')
                            size_hint_y: None
                            height: dp(18)
                        Switch:
                            id: switch_mixte
                            active: False
                            size_hint_y: None
                            height: dp(48)

                BtnPrimary:
                    text: "🗺️  CRÉER UNE PARTIE"
                    on_release: app.creer_partie()

                BoxLayout:
                    size_hint_y: None
                    height: dp(30)
                    Label:
                        text: "── ou rejoindre ──"
                        color: get_color_from_hex('#4a5568')
                        font_size: sp(12)

                ChampsInput:
                    id: input_room
                    hint_text: "Code salle (ex: ABCDEF)"

                BtnSecondary:
                    text: "Rejoindre →"
                    on_release: app.rejoindre_par_code()

# ══════════════════════════════════════════════════════════════
#  ÉCRAN 2 — LOBBY
# ══════════════════════════════════════════════════════════════

<LobbyScreen>:
    name: 'lobby'
    canvas.before:
        Color:
            rgba: get_color_from_hex('#0a1628')
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: dp(24)
        spacing: dp(16)

        # En-tête
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(100)
            spacing: dp(8)

            LabelTitre:
                text: "SALLE D'ATTENTE"
                font_size: sp(22)
                halign: 'center'

            Label:
                id: lbl_room_code
                text: app.room_id
                font_name: 'Roboto'
                font_size: sp(28)
                bold: True
                color: get_color_from_hex('#d4a853')
                halign: 'center'
                letter_spacing: dp(6)

            Label:
                id: lbl_lien
                text: "Appuyez pour copier le lien"
                font_name: 'Roboto'
                font_size: sp(10)
                color: get_color_from_hex('#00c9a7')
                halign: 'center'
                on_touch_down: if self.collide_point(*args[1].pos): app.copier_lien()

        # Liste joueurs
        ScrollView:
            GridLayout:
                id: grid_joueurs
                cols: 2
                spacing: dp(10)
                padding: [0, dp(4)]
                size_hint_y: None
                height: self.minimum_height

        # Actions
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(180)
            spacing: dp(10)

            BtnSecondary:
                text: "🤖  Ajouter un bot"
                on_release: app.ajouter_ia()

            BtnPrimary:
                id: btn_demarrer
                text: "▶  LANCER LA PARTIE"
                on_release: app.demarrer_partie()

# ══════════════════════════════════════════════════════════════
#  ÉCRAN 3 — JEU
# ══════════════════════════════════════════════════════════════

<JeuScreen>:
    name: 'jeu'
    canvas.before:
        Color:
            rgba: get_color_from_hex('#0a1628')
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        spacing: 0

        # Barre actions (pause / quitter)
        BoxLayout:
            size_hint_y: None
            height: dp(40)
            padding: [dp(8), dp(4)]
            spacing: dp(8)
            canvas.before:
                Color:
                    rgba: get_color_from_hex('#0a1628')
                Rectangle:
                    pos: self.pos
                    size: self.size
            Button:
                text: "⏸ Pause"
                size_hint_x: None
                width: dp(90)
                background_normal: ''
                background_color: (1,1,1,0.07)
                color: get_color_from_hex('#f5f0e8')
                font_name: 'Roboto'
                font_size: sp(12)
                on_release: app.basculer_pause()
            Widget:
            Button:
                text: "✕ Quitter"
                size_hint_x: None
                width: dp(90)
                background_normal: ''
                background_color: (0.9,0.22,0.27,0.15)
                color: get_color_from_hex('#e63946')
                font_name: 'Roboto'
                font_size: sp(12)
                on_release: app.confirmer_quitter()

        # Barre scores
        BoxLayout:
            id: scores_bar
            size_hint_y: None
            height: dp(88)
            canvas.before:
                Color:
                    rgba: get_color_from_hex('#112240')
                Rectangle:
                    pos: self.pos
                    size: self.size

        # Barre chrono
        BoxLayout:
            size_hint_y: None
            height: dp(4)
            canvas.before:
                Color:
                    rgba: 1,1,1,0.06
                Rectangle:
                    pos: self.pos
                    size: self.size
            Widget:
                id: chrono_fill
                size_hint_x: 1
                canvas:
                    Color:
                        rgba: app.couleur_chrono
                    Rectangle:
                        pos: self.pos
                        size: self.size

        # Zone centrale
        BoxLayout:
            orientation: 'vertical'
            padding: [dp(16), dp(12)]
            spacing: dp(12)

            # Séquence de lettres
            BoxLayout:
                orientation: 'vertical'
                size_hint_y: None
                height: dp(90)
                spacing: dp(6)

                Label:
                    id: lbl_sequence
                    text: app.lettres_en_cours if app.lettres_en_cours else "…"
                    font_name: 'Roboto'
                    bold: True
                    font_size: sp(36) if len(app.lettres_en_cours) <= 9 else (sp(26) if len(app.lettres_en_cours) <= 15 else sp(18))
                    color: app.couleur_sequence
                    halign: 'center'
                    letter_spacing: dp(4)

                Label:
                    id: lbl_tour
                    text: app.indicateur_tour
                    font_name: 'Roboto'
                    font_size: sp(11)
                    color: get_color_from_hex('#00c9a7')
                    halign: 'center'

                Label:
                    id: lbl_poss
                    text: app.nb_possibilites
                    font_name: 'Roboto'
                    font_size: sp(10)
                    color: get_color_from_hex('#4a5568')
                    halign: 'center'

            # Historique drapeaux
            ScrollView:
                size_hint_y: None
                height: dp(60)
                do_scroll_y: False
                GridLayout:
                    id: historique_drapeaux
                    rows: 1
                    spacing: dp(8)
                    padding: [dp(4), 0]
                    size_hint_x: None
                    width: self.minimum_width

            # Clavier
            GridLayout:
                id: clavier_grille
                cols: 7
                spacing: dp(4)
                size_hint_y: None
                height: dp(200)

            # Bouton langue au chat
            BtnDanger:
                id: btn_langue
                text: "🗣  DONNER MA LANGUE AU CHAT"
                on_release: app.demander_langue_au_chat()

# ══════════════════════════════════════════════════════════════
#  ÉCRAN 4 — FIN
# ══════════════════════════════════════════════════════════════

<FinScreen>:
    name: 'fin'
    canvas.before:
        Color:
            rgba: get_color_from_hex('#0a1628')
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: dp(32)
        spacing: dp(24)
        halign: 'center'

        Label:
            text: "👑"
            font_size: sp(64)
            size_hint_y: None
            height: dp(80)

        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(80)
            Label:
                text: "VAINQUEUR"
                font_name: 'Roboto'
                font_size: sp(11)
                color: get_color_from_hex('#00c9a7')
                letter_spacing: dp(3)
            Label:
                id: lbl_gagnant
                text: app.nom_gagnant
                font_name: 'Roboto'
                bold: True
                font_size: sp(32)
                color: get_color_from_hex('#d4a853')

        # Stats
        GridLayout:
            cols: 3
            spacing: dp(10)
            size_hint_y: None
            height: dp(90)

            BoxLayout:
                orientation: 'vertical'
                canvas.before:
                    Color:
                        rgba: 1,1,1,0.04
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(10)]
                Label:
                    id: stat_pays
                    text: "0"
                    font_name: 'Roboto'
                    bold: True
                    font_size: sp(28)
                    color: get_color_from_hex('#00c9a7')
                Label:
                    text: "PAYS"
                    font_name: 'Roboto'
                    font_size: sp(9)
                    color: get_color_from_hex('#4a5568')

            BoxLayout:
                orientation: 'vertical'
                canvas.before:
                    Color:
                        rgba: 1,1,1,0.04
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(10)]
                Label:
                    id: stat_tours
                    text: "0"
                    font_name: 'Roboto'
                    bold: True
                    font_size: sp(28)
                    color: get_color_from_hex('#00c9a7')
                Label:
                    text: "TOURS"
                    font_name: 'Roboto'
                    font_size: sp(9)
                    color: get_color_from_hex('#4a5568')

            BoxLayout:
                orientation: 'vertical'
                canvas.before:
                    Color:
                        rgba: 1,1,1,0.04
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(10)]
                Label:
                    id: stat_vies
                    text: "0"
                    font_name: 'Roboto'
                    bold: True
                    font_size: sp(28)
                    color: get_color_from_hex('#00c9a7')
                Label:
                    text: "VIES"
                    font_name: 'Roboto'
                    font_size: sp(9)
                    color: get_color_from_hex('#4a5568')

        BtnSecondary:
            text: "🗺️  Voir les pays joués"
            on_release: app.afficher_pays_joues()

        BoxLayout:
            size_hint_y: None
            height: dp(52)
            spacing: dp(10)
            BtnSecondary:
                text: "← Accueil"
                on_release: app.retour_accueil()
            BtnPrimary:
                text: "↺  Rejouer"
                on_release: app.rejouer()
"""


# ──────────────────────────────────────────────────────────────
#  APPLICATION PRINCIPALE
# ──────────────────────────────────────────────────────────────

class PaysGameApp(App):

    # ── Properties (liées au KV) ───────────────────────────────
    room_id           = StringProperty("——")
    lettres_en_cours  = StringProperty("")
    indicateur_tour   = StringProperty("En attente…")
    nb_possibilites   = StringProperty("")
    nom_gagnant       = StringProperty("—")
    couleur_sequence  = ListProperty([0.96, 0.94, 0.91, 1])   # papier
    couleur_chrono    = ListProperty([0, 0.79, 0.66, 1])        # teal

    # ── État interne ───────────────────────────────────────────
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.joueur_id     = str(uuid.uuid4())
        self.nom_joueur    = "Joueur"
        self.langue        = "fr"
        self.mode_mixte    = False
        self.temps_max     = 15
        self.vies_depart   = 10
        self.est_createur  = False
        self.mode_connecte = False

        self.ws            = None          # WebSocket actif
        self.ws_loop       = None          # event loop asyncio dédié
        self.ws_thread     = None

        self.pays_local       = []
        self.pays_joues       = set()   # set de nom_normalise
        self.pays_joues_liste = []      # liste enrichie {pays, cible, valeur_jouee}
        self.en_pause         = False   # état pause

        # État solo
        self.joueurs_solo  = []
        self.index_tour    = 0
        self.sequence      = ""
        self.est_mon_tour  = False
        self.joueur_fautif = None
        self.nb_tours      = 0

        self._chrono_event = None
        self._temps_restant = 15

    # ──────────────────────────────────────────────────────────
    #  BUILD
    # ──────────────────────────────────────────────────────────

    def build(self):
        self.root = Builder.load_string(KV)
        return self.root

    def on_start(self):
        self._charger_pays_local("fr")
        self._lancer_loop_asyncio()

    # ──────────────────────────────────────────────────────────
    #  LOOP ASYNCIO (thread dédié pour WebSockets)
    # ──────────────────────────────────────────────────────────

    def _lancer_loop_asyncio(self):
        self.ws_loop = asyncio.new_event_loop()
        self.ws_thread = threading.Thread(
            target=self.ws_loop.run_forever,
            daemon=True
        )
        self.ws_thread.start()

    def _run_async(self, coro):
        """Lance une coroutine dans la loop dédiée."""
        asyncio.run_coroutine_threadsafe(coro, self.ws_loop)

    # ──────────────────────────────────────────────────────────
    #  DONNÉES PAYS
    # ──────────────────────────────────────────────────────────

    def _charger_pays_local(self, langue: str):
        try:
            with open(f"pays_{langue}.json", "r", encoding="utf-8") as f:
                self.pays_local = json.load(f)
        except FileNotFoundError:
            self.pays_local = [
                {"nom": "FRANCE", "capitale": "PARIS", "code": "fr",
                 "nom_normalise": "FRANCE", "capitale_normalisee": "PARIS"},
                {"nom": "ALLEMAGNE", "capitale": "BERLIN", "code": "de",
                 "nom_normalise": "ALLEMAGNE", "capitale_normalisee": "BERLIN"},
                {"nom": "ESPAGNE", "capitale": "MADRID", "code": "es",
                 "nom_normalise": "ESPAGNE", "capitale_normalisee": "MADRID"},
                {"nom": "ITALIE", "capitale": "ROME", "code": "it",
                 "nom_normalise": "ITALIE", "capitale_normalisee": "ROME"},
                {"nom": "CANADA", "capitale": "OTTAWA", "code": "ca",
                 "nom_normalise": "CANADA", "capitale_normalisee": "OTTAWA"},
                {"nom": "CHINE", "capitale": "PEKIN", "code": "cn",
                 "nom_normalise": "CHINE", "capitale_normalisee": "PEKIN"},
                {"nom": "JAPON", "capitale": "TOKYO", "code": "jp",
                 "nom_normalise": "JAPON", "capitale_normalisee": "TOKYO"},
                {"nom": "BELGIQUE", "capitale": "BRUXELLES", "code": "be",
                 "nom_normalise": "BELGIQUE", "capitale_normalisee": "BRUXELLES"},
            ]
            self._toast("⚠️ Fichier pays non trouvé — mode démo")

    def _chercher_possibilites(self, seq: str):
        """Retourne les pays dont le nom (ou capitale en mode mixte) commence par seq.
        Chaque résultat a un champ '_cible' : 'nom_normalise' ou 'capitale_normalisee'
        indiquant quel champ matche, pour que l'IA sache quelle lettre jouer.
        """
        if not seq:
            # Retourner tous les pays avec _cible par défaut
            return [{**p, "_cible": "nom_normalise"} for p in self.pays_local]
        s = normaliser(seq)
        resultats = []
        for p in self.pays_local:
            if p["nom_normalise"].startswith(s):
                resultats.append({**p, "_cible": "nom_normalise"})
            elif self.mode_mixte and p.get("capitale_normalisee", "").startswith(s):
                resultats.append({**p, "_cible": "capitale_normalisee"})
        return resultats

    def _est_complet(self, seq: str):
        s = normaliser(seq)
        for p in self.pays_local:
            if p["nom_normalise"] == s:
                return p
            if self.mode_mixte and p.get("capitale_normalisee") == s:
                return p
        return None

    # ──────────────────────────────────────────────────────────
    #  ACCUEIL
    # ──────────────────────────────────────────────────────────

    def _lire_config(self):
        ecran = self.root.get_screen("accueil")
        self.nom_joueur = ecran.ids.input_nom.text.strip() or "Joueur"
        self.langue     = "fr" if "Français" in ecran.ids.spin_langue.text else "en"
        self.mode_mixte = ecran.ids.switch_mixte.active
        self.temps_max  = int(ecran.ids.spin_temps.text.split()[0])
        self.vies_depart = int(ecran.ids.spin_vies.text.split()[0])
        self._charger_pays_local(self.langue)

    def creer_partie(self):
        self._lire_config()
        self.est_createur = True
        self._run_async(self._tenter_connexion_serveur(creer=True))

    def rejoindre_par_code(self):
        self._lire_config()
        ecran = self.root.get_screen("accueil")
        code = ecran.ids.input_room.text.strip().upper()
        if len(code) != 6:
            self._toast("Code invalide (6 lettres)", "error")
            return
        self.est_createur = False
        self.room_id = code
        self._run_async(self._tenter_connexion_serveur(creer=False))

    # ──────────────────────────────────────────────────────────
    #  WEBSOCKET
    # ──────────────────────────────────────────────────────────

    async def _tenter_connexion_serveur(self, creer: bool):
        try:
            if creer:
                import urllib.request
                config = {
                    "langue": self.langue,
                    "mode_mixte": self.mode_mixte,
                    "vies": self.vies_depart,
                    "temps": self.temps_max,
                    "max_joueurs": 8,
                }
                req = urllib.request.Request(
                    f"{SERVEUR_HTTP}/parties",
                    data=json.dumps(config).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    data = json.loads(resp.read())
                self.room_id = data["room_id"]

            uri = f"{SERVEUR_WS}/ws/{self.room_id}/{self.joueur_id}/{self.nom_joueur}"
            async with websockets.connect(uri, ping_interval=20) as ws:
                self.ws = ws
                self.mode_connecte = True
                Clock.schedule_once(lambda dt: self._afficher_lobby(), 0)
                await self._recevoir_messages(ws)

        except Exception as e:
            self.ws = None
            self.mode_connecte = False
            Clock.schedule_once(lambda dt: self._lancer_mode_solo(), 0)

    async def _recevoir_messages(self, ws):
        try:
            async for raw in ws:
                msg = json.loads(raw)
                Clock.schedule_once(lambda dt, m=msg: self._traiter_message(m), 0)
        except websockets.ConnectionClosed:
            Clock.schedule_once(lambda dt: self._toast("🔌 Déconnecté", "error"), 0)

    def _envoyer_ws(self, data: dict):
        if self.ws and self.mode_connecte:
            self._run_async(self.ws.send(json.dumps(data)))

    # ──────────────────────────────────────────────────────────
    #  TRAITEMENT MESSAGES SERVEUR
    # ──────────────────────────────────────────────────────────

    def _traiter_message(self, msg: dict):
        t = msg.get("type", "")

        if t in ("etat", "joueur_rejoint", "joueur_parti"):
            self._sync_etat(msg)

        elif t == "partie_demarree":
            self._sync_etat(msg)
            self._aller_ecran("jeu")
            self._toast("🎮 La partie commence !")

        elif t == "nouveau_tour":
            self._sync_etat(msg)
            self.joueur_fautif = msg.get("joueur_fautif", None)  # reset au nouveau tour
            self._lancer_chrono(msg.get("config", {}).get("temps", self.temps_max))
            self.nb_tours += 1

        elif t == "sequence_invalide":
            self._sync_etat(msg)
            self._flash_sequence(invalide=True)
            self._toast(msg.get("message", ""), "warn")

        elif t == "mot_complet":
            self._sync_etat(msg)
            self._flash_sequence(complet=True)
            self._ajouter_drapeau(msg.get("pays", {}))
            self._toast(msg.get("message", ""), "warn")

        elif t == "langue_au_chat":
            self._sync_etat(msg)
            if msg.get("interpelle") == self.joueur_id:
                Clock.schedule_once(
                    lambda dt: self._ouvrir_modal_langue(msg.get("message", "")), 0
                )
            else:
                self._toast(msg.get("message", ""), "warn")

        elif t == "verdict_langue_au_chat":
            self._afficher_verdict(msg)

        elif t == "perte_vie":
            self._sync_etat(msg)
            self._toast(msg.get("message", ""), "error" if msg.get("elimine") else "warn")

        elif t == "fin_partie":
            self._sync_etat(msg)
            self._afficher_fin(msg)

        elif t == "chat":
            self._ajouter_chat(msg)

    def _sync_etat(self, msg: dict):
        """Met à jour l'UI depuis un snapshot serveur."""
        seq = msg.get("sequence", "")
        self.lettres_en_cours = (" · ".join(seq)) if seq else ""

        actuel = msg.get("joueur_actuel")
        self.est_mon_tour = actuel == self.joueur_id

        # Récupérer joueur_fautif depuis le snapshot (envoyé par le serveur corrigé)
        self.joueur_fautif = msg.get("joueur_fautif", self.joueur_fautif)

        joueurs = msg.get("joueurs", [])
        nom_actuel = next((j["nom"] for j in joueurs if j["id"] == actuel), "")
        self.indicateur_tour = "⬇ Ton tour !" if self.est_mon_tour else f"Tour de {nom_actuel}"

        if seq:
            poss = self._chercher_possibilites(seq)
            self.nb_possibilites = f"{len(poss)} pays possible{'s' if len(poss) > 1 else ''}" if poss else ""
        else:
            self.nb_possibilites = ""

        self._mettre_a_jour_scores(msg)
        self._activer_clavier(self.est_mon_tour)

    # ──────────────────────────────────────────────────────────
    #  LOBBY
    # ──────────────────────────────────────────────────────────

    def _afficher_lobby(self):
        self._aller_ecran("lobby")
        ecran = self.root.get_screen("lobby")
        ecran.ids.lbl_room_code.text = self.room_id
        ecran.ids.btn_demarrer.disabled = not self.est_createur

    def copier_lien(self):
        from kivy.core.clipboard import Clipboard
        lien = f"pays-game://rejoindre/{self.room_id}"
        Clipboard.copy(lien)
        self._toast("🔗 Lien copié !")

    def _mettre_a_jour_grille_joueurs(self, joueurs: list):
        try:
            grid = self.root.get_screen("lobby").ids.grid_joueurs
        except Exception:
            return
        grid.clear_widgets()
        avatars = ['🧑', '👩', '🧔', '👱', '🧕', '👨‍💻', '🧙', '🦊']
        for i, j in enumerate(joueurs):
            card = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(4),
                             size_hint_y=None, height=dp(80))
            with card.canvas.before:
                from kivy.graphics import Color, RoundedRectangle
                Color(rgba=(1, 1, 1, 0.04))
                self._rr = RoundedRectangle(pos=card.pos, size=card.size, radius=[dp(10)])
            card.add_widget(Label(
                text=f"{'🤖' if j.get('est_ia') else avatars[i % len(avatars)]}",
                font_size='24sp'
            ))
            card.add_widget(Label(
                text=j['nom'], font_name='Roboto', font_size='13sp',
                color=COULEUR_PAPIER, bold=True
            ))
            tag = 'BOT' if j.get('est_ia') else ('MOI' if j['id'] == self.joueur_id else 'EN LIGNE')
            card.add_widget(Label(
                text=tag, font_name='Roboto', font_size='10sp',
                color=COULEUR_TEAL
            ))
            grid.add_widget(card)

    def ajouter_ia(self):
        if self.mode_connecte:
            import urllib.request
            try:
                req = urllib.request.Request(
                    f"{SERVEUR_HTTP}/parties/{self.room_id}/ia",
                    method="POST"
                )
                urllib.request.urlopen(req, timeout=3)
            except Exception:
                self._toast("Serveur indisponible", "error")
        else:
            self._ajouter_ia_locale()

    def demarrer_partie(self):
        if self.mode_connecte:
            import urllib.request
            try:
                req = urllib.request.Request(
                    f"{SERVEUR_HTTP}/parties/{self.room_id}/demarrer?joueur_id={self.joueur_id}",
                    method="POST"
                )
                urllib.request.urlopen(req, timeout=3)
            except Exception:
                self._toast("Erreur serveur", "error")
        else:
            self._demarrer_solo()

    # ──────────────────────────────────────────────────────────
    #  CLAVIER
    # ──────────────────────────────────────────────────────────

    def _construire_clavier(self):
        try:
            grille = self.root.get_screen("jeu").ids.clavier_grille
        except Exception:
            return
        grille.clear_widgets()
        for lettre in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            btn = Factory.ToucheClavier(text=lettre)
            btn.bind(on_release=lambda inst, l=lettre: self._appuyer_touche(l))
            grille.add_widget(btn)

    def _activer_clavier(self, actif: bool):
        try:
            grille = self.root.get_screen("jeu").ids.clavier_grille
            btn_langue = self.root.get_screen("jeu").ids.btn_langue
        except Exception:
            return
        for child in grille.children:
            child.disabled = not actif
        # Langue au chat disponible quand :
        # - c'est MON tour (actif=True)
        # - ET la séquence a été posée par l'adversaire (au moins 1 lettre)
        # - ET ce n'est pas moi qui ai posé la dernière lettre
        langue_possible = actif and len(self.sequence) > 0 and self.joueur_fautif != self.joueur_id
        btn_langue.disabled = not langue_possible

    def _appuyer_touche(self, lettre: str):
        if not self.est_mon_tour:
            return
        if self.mode_connecte:
            self._envoyer_ws({"action": "lettre", "lettre": lettre})
        else:
            self._traiter_lettre_solo(lettre)

    # ──────────────────────────────────────────────────────────
    #  CHRONO
    # ──────────────────────────────────────────────────────────

    def _lancer_chrono(self, secondes: int):
        if self._chrono_event:
            self._chrono_event.cancel()
        self._temps_restant = secondes
        self.temps_max = secondes
        self._tick_chrono(0)
        self._chrono_event = Clock.schedule_interval(self._tick_chrono, 1)

    def _tick_chrono(self, dt):
        try:
            fill = self.root.get_screen("jeu").ids.chrono_fill
        except Exception:
            return
        pct = self._temps_restant / max(self.temps_max, 1)
        fill.width = fill.parent.width * pct

        if self._temps_restant <= 5:
            self.couleur_chrono = [0.9, 0.22, 0.27, 1]  # crimson
        else:
            self.couleur_chrono = [0, 0.79, 0.66, 1]  # teal

        self._temps_restant -= 1
        if self._temps_restant < 0:
            if self._chrono_event:
                self._chrono_event.cancel()
            if not self.mode_connecte and self.est_mon_tour:
                self._perdre_vie_solo(self.joueur_id, "⏰ Temps écoulé !")

    # ──────────────────────────────────────────────────────────
    #  SCORES
    # ──────────────────────────────────────────────────────────

    def _mettre_a_jour_scores(self, msg: dict):
        try:
            bar = self.root.get_screen("jeu").ids.scores_bar
        except Exception:
            return
        bar.clear_widgets()
        joueurs = msg.get("joueurs", [])
        actuel  = msg.get("joueur_actuel")
        vies_max = msg.get("config", {}).get("vies", self.vies_depart)

        for i, j in enumerate(joueurs):
            actif = j["id"] == actuel
            col = BoxLayout(orientation='vertical', padding=[dp(10), dp(8)], spacing=dp(4))

            # Fond actif
            if actif:
                with col.canvas.before:
                    from kivy.graphics import Color, Rectangle
                    Color(rgba=(0, 0.79, 0.66, 0.08))
                    Rectangle(pos=col.pos, size=col.size)

            # Nom du joueur
            col.add_widget(Label(
                text=f"{'🤖' if j.get('est_ia') else ''}{j['nom']}",
                font_name='Roboto',
                font_size='10sp',
                color=COULEUR_TEAL if actif else (*COULEUR_MUTED[:3], 0.7),
                bold=actif,
                halign='center',
                size_hint_y=None,
                height=dp(16)
            ))

            # Nombre de vies en chiffre — bien visible
            vies_restantes = j["vies"]
            couleur_vies = (
                COULEUR_TEAL    if vies_restantes > vies_max * 0.5 else
                COULEUR_AMBER   if vies_restantes > vies_max * 0.25 else
                COULEUR_CRIMSON
            )
            col.add_widget(Label(
                text=f"❤️ {vies_restantes}/{vies_max}",
                font_name='Roboto',
                bold=True,
                font_size='13sp',
                color=couleur_vies,
                halign='center',
                size_hint_y=None,
                height=dp(20)
            ))

            # Points de vie visuels (petits ronds)
            dots_layout = BoxLayout(
                size_hint_y=None, height=dp(8),
                spacing=dp(2), padding=[0, 0]
            )
            for k in range(vies_max):
                from kivy.uix.widget import Widget
                from kivy.graphics import Color, Ellipse
                dot = Widget(size_hint=(None, None), size=(dp(6), dp(6)))
                with dot.canvas:
                    Color(rgba=COULEUR_CRIMSON if k < vies_restantes else (1, 1, 1, 0.1))
                    Ellipse(pos=dot.pos, size=dot.size)
                dots_layout.add_widget(dot)
            col.add_widget(dots_layout)
            bar.add_widget(col)

            if i < len(joueurs) - 1:
                bar.add_widget(Label(
                    text="VS", font_name='Roboto', font_size='10sp',
                    color=COULEUR_MUTED, size_hint_x=None, width=dp(30)
                ))

    # ──────────────────────────────────────────────────────────
    #  DRAPEAUX
    # ──────────────────────────────────────────────────────────

    def _ajouter_drapeau(self, pays: dict, valeur_jouee: str = None):
        """Ajoute un drapeau dans l'historique.
        valeur_jouee : le mot exact joué (nom ou capitale selon mode mixte).
        """
        if not pays:
            return
        try:
            histo = self.root.get_screen("jeu").ids.historique_drapeaux
        except Exception:
            return

        # En mode mixte, afficher la valeur jouée (nom ou capitale)
        # En mode normal, afficher le nom du pays
        if valeur_jouee:
            texte_affiche = valeur_jouee
        else:
            texte_affiche = pays.get('nom', '')

        # Largeur adaptée à la longueur du texte
        largeur = max(dp(56), dp(8) * min(len(texte_affiche), 12))

        col = BoxLayout(orientation='vertical', size_hint=(None, 1), width=largeur,
                        spacing=dp(2), padding=[dp(2), dp(2)])
        col.add_widget(AsyncImage(
            source=f"https://flagcdn.com/w80/{pays.get('code','fr')}.png",
            size_hint=(1, None),
            height=dp(32),
            fit_mode="contain"
        ))
        col.add_widget(Label(
            text=texte_affiche[:14],
            font_name='Roboto',
            font_size='7sp',
            color=COULEUR_MUTED,
            halign='center',
            text_size=(largeur - dp(4), None)
        ))
        histo.add_widget(col)

    # ──────────────────────────────────────────────────────────
    #  LANGUE AU CHAT
    # ──────────────────────────────────────────────────────────

    def demander_langue_au_chat(self):
        if self.mode_connecte:
            self._envoyer_ws({"action": "langue_au_chat"})
        else:
            self._demander_langue_locale()

    def _ouvrir_modal_langue(self, texte: str = ""):
        # Stopper le chrono pendant que le joueur répond
        if self._chrono_event:
            self._chrono_event.cancel()
            self._chrono_event = None
        content = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(14))
        content.add_widget(Label(
            text="🗣️", font_size='40sp', size_hint_y=None, height=dp(52)
        ))
        content.add_widget(Label(
            text="Langue au chat !",
            font_name='Roboto', bold=True, font_size='18sp',
            color=COULEUR_PAPIER, size_hint_y=None, height=dp(28)
        ))
        content.add_widget(Label(
            text=texte or "Quel pays avais-tu en tête ?",
            font_name='Roboto', font_size='13sp',
            color=(*COULEUR_PAPIER[:3], 0.7),
            size_hint_y=None, height=dp(48),
            text_size=(dp(280), None), halign='center'
        ))
        saisie = TextInput(
            hint_text="FRANCE…",
            font_name='Roboto',
            font_size='18sp',
            halign='center',
            background_color=(1, 1, 1, 0.06),
            foreground_color=COULEUR_PAPIER,
            size_hint_y=None, height=dp(52),
            multiline=False
        )
        content.add_widget(saisie)

        popup = Popup(
            title="",
            content=content,
            size_hint=(0.9, None),
            height=dp(340),
            background_color=(*COULEUR_CARD[:3], 0.98),
            separator_height=0,
        )

        btn_valider = Button(
            text="Valider",
            background_normal='',
            background_color=COULEUR_TEAL,
            color=COULEUR_FOND,
            font_name='Roboto', bold=True,
            size_hint_y=None, height=dp(48)
        )

        def valider(instance):
            rep = saisie.text.strip()
            popup.dismiss()
            if self.mode_connecte:
                self._envoyer_ws({"action": "reponse_langue_au_chat", "pays": rep})
            else:
                self._evaluer_reponse_locale(rep)
            # Le chrono reprendra au prochain tour via _nouveau_tour_solo

        btn_valider.bind(on_release=valider)
        saisie.bind(on_text_validate=valider)
        content.add_widget(btn_valider)
        popup.open()
        Clock.schedule_once(lambda dt: setattr(saisie, 'focus', True), 0.1)

    def _afficher_verdict(self, msg: dict):
        valide = msg.get("valide", False)
        content = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(12))
        content.add_widget(Label(
            text="✅" if valide else "❌",
            font_size='40sp', size_hint_y=None, height=dp(52)
        ))
        content.add_widget(Label(
            text="Bravo !" if valide else "Perdu !",
            font_name='Roboto', bold=True, font_size='18sp',
            color=COULEUR_TEAL if valide else COULEUR_CRIMSON,
            size_hint_y=None, height=dp(28)
        ))
        content.add_widget(Label(
            text=msg.get("message", ""),
            font_name='Roboto', font_size='13sp',
            color=(*COULEUR_PAPIER[:3], 0.8),
            size_hint_y=None, height=dp(60),
            text_size=(dp(280), None), halign='center'
        ))
        popup = Popup(
            title="", content=content,
            size_hint=(0.85, None), height=dp(250),
            background_color=(*COULEUR_CARD[:3], 0.98),
            separator_height=0,
            auto_dismiss=True
        )
        btn = Button(
            text="OK",
            background_normal='', background_color=COULEUR_TEAL,
            color=COULEUR_FOND, font_name='Roboto', bold=True,
            size_hint_y=None, height=dp(46)
        )
        btn.bind(on_release=lambda x: popup.dismiss())
        content.add_widget(btn)
        popup.open()

    # ──────────────────────────────────────────────────────────
    #  TOASTS
    # ──────────────────────────────────────────────────────────

    def _toast(self, texte: str, niveau: str = ""):
        couleurs = {
            "error": COULEUR_CRIMSON,
            "warn":  COULEUR_AMBER,
            "":      COULEUR_TEAL,
        }
        couleur = couleurs.get(niveau, COULEUR_TEAL)

        content = BoxLayout(padding=[dp(14), dp(10)])
        content.add_widget(Label(
            text=texte,
            font_name='Roboto',
            font_size='13sp',
            color=COULEUR_PAPIER,
            text_size=(Window.width * 0.75, None),
            halign='center'
        ))
        popup = Popup(
            title="", content=content,
            size_hint=(0.85, None), height=dp(64),
            background_color=(0.07, 0.09, 0.12, 0.95),
            separator_height=0,
            auto_dismiss=True
        )
        with popup.canvas.before:
            from kivy.graphics import Color, Line
            Color(rgba=couleur)
            Line(rectangle=(popup.x, popup.y, popup.width, popup.height), width=1.5)

        popup.open()
        Clock.schedule_once(lambda dt: popup.dismiss(), 3.0)

    # ──────────────────────────────────────────────────────────
    #  ANIMATIONS
    # ──────────────────────────────────────────────────────────

    def _flash_sequence(self, invalide=False, complet=False):
        if invalide:
            self.couleur_sequence = [*COULEUR_CRIMSON[:3], 1]
        elif complet:
            self.couleur_sequence = [*COULEUR_TEAL[:3], 1]
        Clock.schedule_once(
            lambda dt: setattr(self, 'couleur_sequence', [0.96, 0.94, 0.91, 1]), 0.6
        )

    # ──────────────────────────────────────────────────────────
    #  MODE SOLO — IA LOCALE
    # ──────────────────────────────────────────────────────────

    def _lancer_mode_solo(self):
        self.mode_connecte = False
        self.joueurs_solo = [
            {"id": self.joueur_id, "nom": self.nom_joueur,
             "vies": self.vies_depart, "en_vie": True, "est_ia": False},
            {"id": "ia", "nom": "🤖 Ordinateur",
             "vies": self.vies_depart, "en_vie": True, "est_ia": True},
        ]
        self.index_tour   = 0
        self.sequence     = ""
        self.pays_joues   = set()
        self.pays_joues_liste = []
        self.nb_tours     = 0
        self.joueur_fautif = None

        self.room_id = "SOLO"
        self._afficher_lobby()
        ecran = self.root.get_screen("lobby")
        ecran.ids.btn_demarrer.disabled = False
        self._mettre_a_jour_grille_joueurs(self.joueurs_solo)
        self._toast("🔌 Serveur non disponible — mode solo vs IA", "warn")

    def _ajouter_ia_locale(self):
        if len(self.joueurs_solo) >= 4:
            return
        self.joueurs_solo.append({
            "id": f"ia{len(self.joueurs_solo)}",
            "nom": "🤖 Bot",
            "vies": self.vies_depart,
            "en_vie": True,
            "est_ia": True,
        })
        self._mettre_a_jour_grille_joueurs(self.joueurs_solo)

    def _demarrer_solo(self):
        self._aller_ecran("jeu")
        self._construire_clavier()
        self._nouveau_tour_solo()

    def _joueur_actuel_solo(self):
        return self.joueurs_solo[self.index_tour]

    def _nouveau_tour_solo(self, reset_sequence=True):
        # reset_sequence=True uniquement après une perte de vie ou fin de round
        # reset_sequence=False quand on passe juste le tour à l'adversaire
        if reset_sequence:
            self.sequence = ""
            self.joueur_fautif = None
        self.nb_tours += 1
        j = self._joueur_actuel_solo()
        self.est_mon_tour = j["id"] == self.joueur_id

        snap = {
            "sequence": self.sequence,
            "joueur_actuel": j["id"],
            "joueurs": self.joueurs_solo,
            "config": {"vies": self.vies_depart},
        }
        self._sync_etat(snap)
        self._lancer_chrono(self.temps_max)

        if j["est_ia"]:
            self._activer_clavier(False)
            Clock.schedule_once(lambda dt: self._ia_jouer_solo(), random.uniform(1.0, 2.2))

    def _traiter_lettre_solo(self, lettre: str):
        if not self.est_mon_tour:
            return
        # On travaille toujours sur la séquence normalisée
        nouvelle_seq = normaliser(self.sequence) + normaliser(lettre)
        possibilites = self._chercher_possibilites(nouvelle_seq)

        if not possibilites:
            self._flash_sequence(invalide=True)
            self.sequence = nouvelle_seq
            self.joueur_fautif = self.joueur_id
            snap = {"sequence": nouvelle_seq, "joueur_actuel": self.joueur_id,
                    "joueurs": self.joueurs_solo, "config": {"vies": self.vies_depart}}
            self._sync_etat(snap)
            self._toast("⚠️ Séquence invalide — l'IA peut demander langue au chat", "warn")
            self._passer_suivant_solo()
            return

        self.sequence = nouvelle_seq
        match = self._est_complet(nouvelle_seq)

        if match:
            if match["nom_normalise"] in self.pays_joues:
                self._toast(f"🔁 {match['nom']} déjà joué ! Tu perds une vie.", "error")
                self._perdre_vie_solo(self.joueur_id, "Pays déjà joué")
                return

            # Déterminer si c'est un nom ou une capitale qui a été complété
            champ_complete = "_cible" if "_cible" in match else "nom_normalise"
            valeur_jouee = match.get("capitale") if (
                self.mode_mixte and nouvelle_seq == match.get("capitale_normalisee")
            ) else match.get("nom")
            self.pays_joues.add(match["nom_normalise"])
            self.pays_joues_liste.append({**match, "_valeur_jouee": valeur_jouee})
            self._ajouter_drapeau(match, valeur_jouee)
            self._flash_sequence(complet=True)
            self._toast(f"💀 Tu as complété « {valeur_jouee} » — tu perds une vie !", "warn")
            # Stopper le chrono avant la perte de vie
            if self._chrono_event:
                self._chrono_event.cancel()
                self._chrono_event = None
            Clock.schedule_once(lambda dt: self._perdre_vie_solo(self.joueur_id, "Mot complet"), 1.5)
        else:
            snap = {"sequence": nouvelle_seq, "joueur_actuel": self.joueur_id,
                    "joueurs": self.joueurs_solo, "config": {"vies": self.vies_depart}}
            self._sync_etat(snap)
            self._passer_suivant_solo()

    def _ia_jouer_solo(self):
        seq = self.sequence
        possibilites = self._chercher_possibilites(seq)

        if not possibilites:
            # L'IA interpelle le joueur si c'est lui le fautif
            if self.joueur_fautif == self.joueur_id:
                Clock.schedule_once(
                    lambda dt: self._ouvrir_modal_langue("L'IA te demande : quel pays visais-tu ?"), 0
                )
            else:
                self._toast("🤖 L'IA donne sa langue au chat ! Elle perd une vie.", "warn")
                self._perdre_vie_solo("ia", "IA piégée")
            return

        seq_norm = normaliser(seq)

        # Filtrer les pays non encore joués
        possibilites_nonjoues = [
            p for p in possibilites
            if p["nom_normalise"] not in self.pays_joues
        ]

        # Si toutes les possibilités ont été jouées → langue au chat car piégée
        if not possibilites_nonjoues:
            self._toast("🤖 L'IA est piégée (tous les pays déjà joués) ! Elle perd une vie.", "warn")
            if self._chrono_event:
                self._chrono_event.cancel()
                self._chrono_event = None
            self._perdre_vie_solo("ia", "Tous pays joués")
            return

        # Stratégie : éviter de compléter si possible, parmi les pays non joués
        cibles_longues = [p for p in possibilites_nonjoues if len(p[p["_cible"]]) > len(seq_norm) + 1]
        cibles = cibles_longues if cibles_longues else possibilites_nonjoues

        cible = random.choice(cibles)
        champ_cible = cible["_cible"]
        lettre_suivante = cible[champ_cible][len(seq_norm)]
        nouvelle_seq = seq_norm + lettre_suivante
        self.sequence = nouvelle_seq
        self.joueur_fautif = "ia"

        match = self._est_complet(nouvelle_seq)
        if match:
            if match["nom_normalise"] in self.pays_joues:
                # Ne devrait plus arriver grâce au filtre, mais sécurité
                self._toast(f"🔁 L'IA a joué {match['nom']} déjà joué ! Elle perd une vie.", "warn")
                if self._chrono_event:
                    self._chrono_event.cancel()
                    self._chrono_event = None
                Clock.schedule_once(lambda dt: self._perdre_vie_solo("ia", "Pays déjà joué"), 0.5)
                return
            valeur_jouee = match.get("capitale") if (
                self.mode_mixte and nouvelle_seq == match.get("capitale_normalisee")
            ) else match.get("nom")
            self.pays_joues.add(match["nom_normalise"])
            self.pays_joues_liste.append({**match, "_valeur_jouee": valeur_jouee})
            self._ajouter_drapeau(match, valeur_jouee)
            snap = {"sequence": nouvelle_seq, "joueur_actuel": "ia",
                    "joueurs": self.joueurs_solo, "config": {"vies": self.vies_depart}}
            self._sync_etat(snap)
            self._flash_sequence(complet=True)
            self._toast(f"💀 L'IA a complété « {valeur_jouee} » — elle perd une vie !", "warn")
            if self._chrono_event:
                self._chrono_event.cancel()
                self._chrono_event = None
            Clock.schedule_once(lambda dt: self._perdre_vie_solo("ia", "Mot complet"), 1.5)
        else:
            snap = {"sequence": nouvelle_seq, "joueur_actuel": "ia",
                    "joueurs": self.joueurs_solo, "config": {"vies": self.vies_depart}}
            self._sync_etat(snap)
            self._passer_suivant_solo()

    def _demander_langue_locale(self):
        """Le joueur demande une langue au chat à l'IA.
        L'IA doit justifier les lettres qu'elle vient de jouer.
        """
        # Stopper le chrono pendant le traitement
        if self._chrono_event:
            self._chrono_event.cancel()
            self._chrono_event = None
        seq = self.sequence
        # L'IA doit trouver un pays qui commence par toute la séquence actuelle
        possibilites = self._chercher_possibilites(seq)
        # Filtrer : le pays doit vraiment commencer par la séquence (pas juste un préfixe partiel)
        seq_norm = normaliser(seq)
        possibilites_valides = [
            p for p in possibilites
            if p[p["_cible"]].startswith(seq_norm)
            and p["nom_normalise"] not in self.pays_joues
        ]
        if possibilites_valides:
            pays = random.choice(possibilites_valides)
            champ = pays["_cible"]
            valeur = pays["nom"] if champ == "nom_normalise" else pays["capitale"]
            self._afficher_verdict({
                "valide": True,
                "message": f"L'IA visait « {valeur} » ({seq}...). Valide ! Tu perds une vie."
            })
            self.pays_joues.add(pays["nom_normalise"])
            self.pays_joues_liste.append({**pays, "_valeur_jouee": valeur})
            self._ajouter_drapeau(pays, valeur)
            Clock.schedule_once(lambda dt: self._perdre_vie_solo(self.joueur_id, "Langue au chat perdue"), 0.5)
        else:
            self._afficher_verdict({
                "valide": False,
                "message": f"L'IA ne peut pas justifier « {seq} » ! Elle perd une vie."
            })
            Clock.schedule_once(lambda dt: self._perdre_vie_solo("ia", "IA sans réponse"), 0.5)

    def _evaluer_reponse_locale(self, pays_propose: str):
        """Évalue la réponse du joueur à une langue au chat.
        Fonctionne en mode normal ET mixte (nom ou capitale).
        """
        norm = normaliser(pays_propose)
        seq_norm = normaliser(self.sequence)

        # Chercher dans les noms ET capitales (mode mixte)
        match = next((p for p in self.pays_local if p["nom_normalise"] == norm), None)
        champ_match = "nom_normalise"
        valeur_affichee = pays_propose

        if not match and self.mode_mixte:
            # Essayer les capitales
            match = next((p for p in self.pays_local if p.get("capitale_normalisee") == norm), None)
            if match:
                champ_match = "capitale_normalisee"
                valeur_affichee = match.get("capitale", pays_propose)

        if not match:
            self._afficher_verdict({"valide": False,
                "message": f"« {pays_propose} » n'existe pas ! Tu perds une vie."})
            Clock.schedule_once(lambda dt: self._perdre_vie_solo(self.joueur_id, "Pays inexistant"), 0.5)
        elif match["nom_normalise"] in self.pays_joues:
            self._afficher_verdict({"valide": False,
                "message": f"« {valeur_affichee} » a déjà été joué ! Tu perds une vie."})
            Clock.schedule_once(lambda dt: self._perdre_vie_solo(self.joueur_id, "Pays déjà joué"), 0.5)
        elif not match[champ_match].startswith(seq_norm):
            self._afficher_verdict({"valide": False,
                "message": f"« {valeur_affichee} » ne commence pas par « {self.sequence} » ! Tu perds une vie."})
            Clock.schedule_once(lambda dt: self._perdre_vie_solo(self.joueur_id, "Pays incohérent"), 0.5)
        else:
            self.pays_joues.add(match["nom_normalise"])
            self.pays_joues_liste.append({**match, "_valeur_jouee": valeur_affichee})
            self._ajouter_drapeau(match, valeur_affichee)
            self._afficher_verdict({"valide": True,
                "message": f"✅ « {valeur_affichee} » commence bien par « {self.sequence} » ! L'IA perd une vie."})
            Clock.schedule_once(lambda dt: self._perdre_vie_solo("ia", "Langue au chat perdue"), 0.5)

    def _perdre_vie_solo(self, joueur_id: str, raison: str):
        """Retire une vie et gère l'élimination. Fonctionne pour tous les modes."""
        if self._chrono_event:
            self._chrono_event.cancel()
            self._chrono_event = None

        j = next((x for x in self.joueurs_solo if x["id"] == joueur_id), None)
        if not j:
            return

        j["vies"] -= 1
        if j["vies"] <= 0:
            j["vies"] = 0
            j["en_vie"] = False
            # Toast d'élimination
            self._toast(f"💀 {j['nom']} est éliminé !", "error")

        # Mettre à jour l'affichage des scores immédiatement
        snap = {"sequence": self.sequence, "joueur_actuel": None,
                "joueurs": self.joueurs_solo, "config": {"vies": self.vies_depart}}
        self._mettre_a_jour_scores(snap)

        vivants = [x for x in self.joueurs_solo if x["en_vie"]]
        if len(vivants) <= 1:
            Clock.schedule_once(lambda dt: self._afficher_fin_solo(vivants[0] if vivants else None), 0.8)
            return

        # Celui qui perd repart EN PREMIER (si encore en vie), sinon le suivant
        if j["en_vie"]:
            self.index_tour = self.joueurs_solo.index(j)
        else:
            # Joueur éliminé : passer au suivant vivant
            n = len(self.joueurs_solo)
            idx = self.joueurs_solo.index(j)
            for _ in range(n):
                idx = (idx + 1) % n
                if self.joueurs_solo[idx]["en_vie"]:
                    break
            self.index_tour = idx

        Clock.schedule_once(lambda dt: self._nouveau_tour_solo(), 0.8)

    def _passer_suivant_solo(self):
        n = len(self.joueurs_solo)
        for _ in range(n):
            self.index_tour = (self.index_tour + 1) % n
            if self.joueurs_solo[self.index_tour]["en_vie"]:
                break
        # On NE remet PAS la séquence à zéro — l'adversaire continue sur la même séquence
        Clock.schedule_once(lambda dt: self._nouveau_tour_solo(reset_sequence=False), 0.15)

    # ──────────────────────────────────────────────────────────
    #  FIN DE PARTIE
    # ──────────────────────────────────────────────────────────

    def _afficher_fin(self, msg: dict):
        if self._chrono_event:
            self._chrono_event.cancel()
        gagnant = next((j for j in msg.get("joueurs", []) if j["id"] == msg.get("gagnant")), None)
        self.nom_gagnant = gagnant["nom"] if gagnant else "—"
        ecran = self.root.get_screen("fin")
        ecran.ids.stat_pays.text  = str(len(msg.get("pays_joues", [])))
        ecran.ids.stat_tours.text = str(self.nb_tours)
        ecran.ids.stat_vies.text  = str(gagnant["vies"] if gagnant else 0)
        Clock.schedule_once(lambda dt: self._aller_ecran("fin"), 0.6)

    def _afficher_fin_solo(self, gagnant):
        if self._chrono_event:
            self._chrono_event.cancel()
        self.nom_gagnant = gagnant["nom"] if gagnant else "—"
        ecran = self.root.get_screen("fin")
        ecran.ids.stat_pays.text  = str(len(self.pays_joues_liste))
        ecran.ids.stat_tours.text = str(self.nb_tours)
        ecran.ids.stat_vies.text  = str(gagnant["vies"] if gagnant else 0)
        self._aller_ecran("fin")

    # ──────────────────────────────────────────────────────────
    #  PAUSE / QUITTER / PAYS JOUÉS
    # ──────────────────────────────────────────────────────────

    def basculer_pause(self):
        """Met en pause ou reprend la partie."""
        self.en_pause = not self.en_pause
        if self.en_pause:
            # Stopper le chrono
            if self._chrono_event:
                self._chrono_event.cancel()
                self._chrono_event = None
            # Désactiver clavier et langue au chat
            try:
                grille = self.root.get_screen("jeu").ids.clavier_grille
                for child in grille.children:
                    child.disabled = True
                self.root.get_screen("jeu").ids.btn_langue.disabled = True
            except Exception:
                pass
            self._afficher_popup_pause()
        else:
            self._reprendre_partie()

    def _afficher_popup_pause(self):
        content = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(16))
        content.add_widget(Label(
            text="⏸", font_size="48sp", size_hint_y=None, height=dp(60)
        ))
        content.add_widget(Label(
            text="PARTIE EN PAUSE",
            font_name="Roboto", bold=True, font_size="18sp",
            color=COULEUR_PAPIER, size_hint_y=None, height=dp(28)
        ))
        self._popup_pause = Popup(
            title="", content=content,
            size_hint=(0.8, None), height=dp(200),
            background_color=(*COULEUR_CARD[:3], 0.97),
            separator_height=0,
            auto_dismiss=False
        )
        btn = Button(
            text="▶  Reprendre",
            background_normal="", background_color=COULEUR_TEAL,
            color=COULEUR_FOND, font_name="Roboto", bold=True,
            size_hint_y=None, height=dp(48)
        )
        btn.bind(on_release=lambda x: self._reprendre_depuis_popup())
        content.add_widget(btn)
        self._popup_pause.open()

    def _reprendre_depuis_popup(self):
        if hasattr(self, "_popup_pause"):
            self._popup_pause.dismiss()
        self._reprendre_partie()

    def _reprendre_partie(self):
        self.en_pause = False
        # Relancer le chrono avec le temps restant
        if self._temps_restant > 0:
            self._chrono_event = Clock.schedule_interval(self._tick_chrono, 1)
        # Réactiver clavier selon le tour
        self._activer_clavier(self.est_mon_tour)

    def confirmer_quitter(self):
        """Demande confirmation avant de quitter la partie."""
        # Mettre en pause automatiquement
        if not self.en_pause:
            if self._chrono_event:
                self._chrono_event.cancel()
                self._chrono_event = None

        content = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(14))
        content.add_widget(Label(
            text="Quitter la partie ?",
            font_name="Roboto", bold=True, font_size="17sp",
            color=COULEUR_PAPIER, size_hint_y=None, height=dp(30)
        ))
        content.add_widget(Label(
            text="La partie sera abandonnée.",
            font_name="Roboto", font_size="13sp",
            color=(*COULEUR_PAPIER[:3], 0.6),
            size_hint_y=None, height=dp(24)
        ))
        popup = Popup(
            title="", content=content,
            size_hint=(0.82, None), height=dp(210),
            background_color=(*COULEUR_CARD[:3], 0.97),
            separator_height=0, auto_dismiss=True
        )
        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        btn_annuler = Button(
            text="Continuer",
            background_normal="", background_color=(1, 1, 1, 0.07),
            color=COULEUR_PAPIER, font_name="Roboto"
        )
        btn_quitter = Button(
            text="Quitter",
            background_normal="", background_color=COULEUR_CRIMSON,
            color=COULEUR_PAPIER, font_name="Roboto", bold=True
        )
        def annuler(x):
            popup.dismiss()
            # Reprendre si pas en pause
            if not self.en_pause:
                self._reprendre_partie()
        def quitter(x):
            popup.dismiss()
            self.retour_accueil()
        btn_annuler.bind(on_release=annuler)
        btn_quitter.bind(on_release=quitter)
        btns.add_widget(btn_annuler)
        btns.add_widget(btn_quitter)
        content.add_widget(btns)
        popup.open()

    def afficher_pays_joues(self):
        """Affiche la liste complète des pays/capitales joués en fin de partie."""
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(16))

        titre = Label(
            text=f"🗺️  {len(self.pays_joues_liste)} mot(s) joué(s)",
            font_name="Roboto", bold=True, font_size="15sp",
            color=COULEUR_TEAL, size_hint_y=None, height=dp(32)
        )
        content.add_widget(titre)

        scroll = ScrollView()
        liste = BoxLayout(
            orientation="vertical", spacing=dp(6),
            size_hint_y=None, padding=[0, dp(4)]
        )
        liste.bind(minimum_height=liste.setter("height"))

        for item in self.pays_joues_liste:
            valeur = item.get("_valeur_jouee") or item.get("nom", "")
            code   = item.get("code", "fr")
            # Ligne : drapeau + texte
            ligne = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
            ligne.add_widget(AsyncImage(
                source=f"https://flagcdn.com/w80/{code}.png",
                size_hint=(None, 1), width=dp(56),
                fit_mode="contain"
            ))
            # En mode mixte, afficher "capitale (Pays)"
            if self.mode_mixte and item.get("_valeur_jouee") and item["_valeur_jouee"] != item.get("nom"):
                texte = f"{item['_valeur_jouee']}  ({item.get('nom', '')})"
            else:
                texte = valeur
            ligne.add_widget(Label(
                text=texte,
                font_name="Roboto", font_size="13sp",
                color=COULEUR_PAPIER, halign="left",
                text_size=(dp(200), None)
            ))
            liste.add_widget(ligne)

        scroll.add_widget(liste)
        content.add_widget(scroll)

        btn_fermer = Button(
            text="Fermer",
            background_normal="", background_color=COULEUR_TEAL,
            color=COULEUR_FOND, font_name="Roboto", bold=True,
            size_hint_y=None, height=dp(46)
        )
        popup = Popup(
            title="", content=content,
            size_hint=(0.92, 0.85),
            background_color=(*COULEUR_CARD[:3], 0.97),
            separator_height=0, auto_dismiss=True
        )
        btn_fermer.bind(on_release=popup.dismiss)
        content.add_widget(btn_fermer)
        popup.open()

    def retour_accueil(self):
        if self._chrono_event:
            self._chrono_event.cancel()
        if self.ws:
            self._run_async(self.ws.close())
            self.ws = None
        self.en_pause = False
        self._aller_ecran("accueil")

    def rejouer(self):
        if self._chrono_event:
            self._chrono_event.cancel()
        if self.mode_connecte:
            self.retour_accueil()
        else:
            self._reinitialiser_partie()
            Clock.schedule_once(lambda dt: self._demarrer_solo(), 0.1)

    def _reinitialiser_partie(self):
        """Remet à zéro TOUTES les données de partie — tous modes, langues, vies, chronos."""
        # Vider l'historique des drapeaux affiché
        try:
            self.root.get_screen("jeu").ids.historique_drapeaux.clear_widgets()
        except Exception:
            pass
        # Reset données de jeu — exhaustif
        self.pays_joues       = set()
        self.pays_joues_liste = []
        self.sequence         = ""
        self.joueur_fautif    = None
        self.nb_tours         = 0
        self.en_pause         = False
        # Reset vies de TOUS les joueurs (mode normal ET mixte ET anglais)
        for j in self.joueurs_solo:
            j["vies"]   = self.vies_depart
            j["en_vie"] = True
        self.index_tour = 0
        # Annuler tout chrono résiduel
        if self._chrono_event:
            self._chrono_event.cancel()
            self._chrono_event = None

    # ──────────────────────────────────────────────────────────
    #  NAVIGATION
    # ──────────────────────────────────────────────────────────

    def _aller_ecran(self, nom: str):
        self.root.current = nom

    def _ajouter_chat(self, msg: dict):
        pass  # Chat visuel non implémenté sur mobile (popup si besoin)


# ──────────────────────────────────────────────────────────────
#  LANCEMENT
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    PaysGameApp().run()
