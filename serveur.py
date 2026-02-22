"""
╔══════════════════════════════════════════════════════════════╗
║           PAYS GAME — Serveur Backend                        ║
║   FastAPI + WebSockets — Python 3.10+                        ║
║                                                              ║
║  Installation :                                              ║
║    pip install fastapi uvicorn[standard] websockets          ║
║                                                              ║
║  Lancement :                                                 ║
║    uvicorn server:app --host 0.0.0.0 --port 8000 --reload    ║
╚══════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import json
import random
import string
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Set
from enum import Enum

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ──────────────────────────────────────────────────────────────
#  APP & CORS
# ──────────────────────────────────────────────────────────────

app = FastAPI(title="Pays Game API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────
#  NORMALISATION & DONNÉES PAYS
# ──────────────────────────────────────────────────────────────

def normaliser(s: str) -> str:
    """Supprime accents, espaces, tirets, apostrophes — aligné avec le JS client."""
    s = unicodedata.normalize("NFD", s.upper()).encode("ascii", "ignore").decode("ascii")
    return s.replace(" ", "").replace("-", "").replace("'", "")


def charger_pays(langue: str) -> List[dict]:
    fichier = f"pays_{langue}.json"
    try:
        with open(fichier, "r", encoding="utf-8") as f:
            pays = json.load(f)
    except FileNotFoundError:
        pays = [{"nom": "FRANCE", "capitale": "PARIS", "code": "fr"}]
    for p in pays:
        p["nom_normalise"]       = normaliser(p.get("nom_normalise") or p.get("nom", ""))
        p["capitale_normalisee"] = normaliser(p.get("capitale_normalisee") or p.get("capitale", ""))
    return pays

PAYS_FR = charger_pays("fr")
PAYS_EN = charger_pays("en")

def get_pays(langue: str) -> List[dict]:
    return PAYS_FR if langue == "fr" else PAYS_EN


def chercher_pays(sequence: str, langue: str, mode_mixte: bool) -> List[dict]:
    """Retourne tous les pays dont le nom commence par `sequence`."""
    seq = normaliser(sequence)
    pays = get_pays(langue)
    resultats = []
    for p in pays:
        if p["nom_normalise"].startswith(seq):
            resultats.append({"type": "pays", **p})
        elif mode_mixte and p["capitale_normalisee"].startswith(seq):
            resultats.append({"type": "capitale", **p})
    return resultats


def est_complet(sequence: str, langue: str, mode_mixte: bool,
                pays_joues_noms: set = None) -> Optional[dict]:
    """Niger ne se complète pas si Nigeria est encore jouable.
    try/except pour éviter tout plantage asynchrone.
    """
    try:
        seq = normaliser(sequence)
        if not seq:
            return None
        pays = get_pays(langue)
        joues = pays_joues_noms if pays_joues_noms is not None else set()
        match = None

        for p in pays:
            if p["nom_normalise"] == seq:
                match = {**p, "type": "pays"}
                break
        if match is None and mode_mixte:
            for p in pays:
                if p.get("capitale_normalisee", "") == seq:
                    match = {**p, "type": "capitale"}
                    break

        if match is None:
            return None

        # Pays plus long encore jouable → pas complet
        for p in pays:
            nom = p["nom_normalise"]
            if nom != seq and nom.startswith(seq) and nom not in joues:
                return None
        if mode_mixte:
            for p in pays:
                cap = p.get("capitale_normalisee", "")
                if cap and cap != seq and cap.startswith(seq) and p["nom_normalise"] not in joues:
                    return None

        return match
    except Exception as e:
        print(f"[est_complet ERROR] seq={sequence!r} err={e}")
        return None

# ──────────────────────────────────────────────────────────────
#  MODÈLES
# ──────────────────────────────────────────────────────────────

class EtatJoueur(BaseModel):
    id: str
    nom: str
    vies: int
    en_vie: bool = True
    est_ia: bool = False


class EtatPartie(str, Enum):
    ATTENTE  = "attente"
    EN_COURS = "en_cours"
    TERMINEE = "terminee"


class Config(BaseModel):
    langue:      str  = "fr"
    vies:        int  = 3
    temps:       int  = 15
    max_joueurs: int  = 8
    mode_mixte:  bool = False
    mode_jeu:    str  = "classique"

# ──────────────────────────────────────────────────────────────
#  CONNEXION WEBSOCKET
# ──────────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.connexions: Dict[str, Dict[str, WebSocket]] = {}

    async def connecter(self, room_id: str, joueur_id: str, ws: WebSocket):
        await ws.accept()
        self.connexions.setdefault(room_id, {})[joueur_id] = ws

    def deconnecter(self, room_id: str, joueur_id: str):
        self.connexions.get(room_id, {}).pop(joueur_id, None)

    async def envoyer(self, room_id: str, joueur_id: str, data: dict):
        ws = self.connexions.get(room_id, {}).get(joueur_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                pass

    async def diffuser(self, room_id: str, data: dict):
        for ws in list(self.connexions.get(room_id, {}).values()):
            try:
                await ws.send_json(data)
            except Exception:
                pass

manager = ConnectionManager()

# ──────────────────────────────────────────────────────────────
#  CLASSE PARTIE
# ──────────────────────────────────────────────────────────────

class Partie:
    def __init__(self, room_id: str, config: Config, createur_id: str):
        self.room_id       = room_id
        self.config        = config
        self.createur_id   = createur_id
        self.etat          = EtatPartie.ATTENTE
        self.joueurs: Dict[str, EtatJoueur] = {}
        self.ordre: List[str] = []
        self.index_tour    = 0
        self.sequence      = ""
        self.pays_joues: List[dict] = []
        self.pays_joues_noms: Set[str] = set()
        self.en_attente_langue_au_chat = False
        self.joueur_interpelle: Optional[str] = None
        self.joueur_fautif: Optional[str] = None
        self.chrono_task: Optional[asyncio.Task] = None
        self.lac_timeout_task: Optional[asyncio.Task] = None
        self.tours_sans_jouer: Dict[str, int] = {}

    # ── Propriétés ────────────────────────────────────────────

    @property
    def joueur_actuel_id(self) -> Optional[str]:
        if not self.ordre:
            return None
        return self.ordre[self.index_tour % len(self.ordre)]

    @property
    def joueurs_vivants(self) -> List[str]:
        """IDs des joueurs encore en vie (humains + IA)."""
        return [jid for jid, j in self.joueurs.items() if j.en_vie]

    def prochain_vivant(self) -> Optional[str]:
        """Passe à l'index suivant en sautant les éliminés."""
        n = len(self.ordre)
        if n == 0:
            return None
        for _ in range(n):
            self.index_tour = (self.index_tour + 1) % n
            jid = self.ordre[self.index_tour]
            if self.joueurs.get(jid) and self.joueurs[jid].en_vie:
                return jid
        return self.joueur_actuel_id

    # ── Snapshot ──────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "type": "etat",
            "room_id": self.room_id,
            "etat": self.etat.value,
            "config": self.config.dict(),
            "joueurs": [j.dict() for j in self.joueurs.values()],
            "ordre": self.ordre,
            "joueur_actuel": self.joueur_actuel_id,
            "sequence": self.sequence,
            "pays_joues": self.pays_joues,
            "en_attente_langue_au_chat": self.en_attente_langue_au_chat,
            "joueur_interpelle": self.joueur_interpelle,
            "joueur_fautif": self.joueur_fautif,
        }

    # ── Chrono ────────────────────────────────────────────────

    def annuler_chrono(self):
        if self.chrono_task and not self.chrono_task.done():
            self.chrono_task.cancel()
        self.chrono_task = None

    async def lancer_chrono(self):
        """Anti-zombie : capture jid + référence de tâche au démarrage."""
        jid = self.joueur_actuel_id
        cette_tache = asyncio.current_task()
        try:
            await asyncio.sleep(self.config.temps)

            # Vérification anti-zombie
            if self.chrono_task is not cette_tache:
                return
            if self.joueur_actuel_id != jid:
                return

            # Petit délai pour laisser les messages WS en retard arriver
            await asyncio.sleep(0.5)

            # Incrémenter AFK
            self.tours_sans_jouer[jid] = self.tours_sans_jouer.get(jid, 0) + 1
            afk = self.tours_sans_jouer[jid]

            if afk >= 3:
                # Élimination directe
                joueur = self.joueurs.get(jid)
                if joueur:
                    joueur.vies = 0
                    joueur.en_vie = False
                await manager.diffuser(self.room_id, {
                    **self.snapshot(),
                    "type": "perte_vie",
                    "joueur_id": jid,
                    "raison": "AFK",
                    "vies_restantes": 0,
                    "elimine": True,
                    "message": f"💤 {self.joueurs[jid].nom if jid in self.joueurs else '?'} éliminé pour inactivité (3 tours) !",
                })
                vivants = self.joueurs_vivants
                if len(vivants) <= 1:
                    await fin_de_partie(self, vivants[0] if vivants else None)
                    return
                self.prochain_vivant()
                await demarrer_tour(self, reset_sequence=True)
            else:
                await self.appliquer_perte_vie(jid, "⏰ Temps écoulé !")
        except asyncio.CancelledError:
            pass

    # ── Perte de vie ──────────────────────────────────────────

    async def appliquer_perte_vie(self, joueur_id: str, raison: str):
        joueur = self.joueurs.get(joueur_id)
        if not joueur:
            return

        joueur.vies -= 1
        if joueur.vies <= 0:
            joueur.vies = 0
            joueur.en_vie = False

        await manager.diffuser(self.room_id, {
            **self.snapshot(),
            "type": "perte_vie",
            "joueur_id": joueur_id,
            "raison": raison,
            "vies_restantes": joueur.vies,
            "elimine": not joueur.en_vie,
            "message": f"💔 {joueur.nom} perd une vie ! ({joueur.vies} restantes)",
        })

        vivants = self.joueurs_vivants
        if len(vivants) <= 1:
            await fin_de_partie(self, vivants[0] if vivants else None)
            return

        # Le joueur qui a perdu recommence (séquence repart de zéro)
        if joueur_id in self.ordre and joueur.en_vie:
            self.index_tour = self.ordre.index(joueur_id)
        else:
            self.prochain_vivant()

        await asyncio.sleep(0.5)
        await demarrer_tour(self, reset_sequence=True)


# ──────────────────────────────────────────────────────────────
#  REGISTRE GLOBAL
# ──────────────────────────────────────────────────────────────

parties: Dict[str, Partie] = {}

def generer_room_id() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=6))

# ──────────────────────────────────────────────────────────────
#  LOGIQUE DE JEU
# ──────────────────────────────────────────────────────────────

async def demarrer_tour(partie: Partie, reset_sequence: bool = True):
    if reset_sequence:
        partie.sequence = ""
        partie.en_attente_langue_au_chat = False
        partie.joueur_interpelle = None
        partie.joueur_fautif = None

    partie.annuler_chrono()

    # FIX-AFK : reset compteur pour ce joueur à chaque nouveau tour
    if partie.joueur_actuel_id:
        partie.tours_sans_jouer[partie.joueur_actuel_id] = 0

    snap = {
        **partie.snapshot(),
        "type": "nouveau_tour",
        "message": f"Tour de {partie.joueurs[partie.joueur_actuel_id].nom}",
    }

    # Avertissement Niger/Nigeria
    if partie.sequence:
        seq_norm = normaliser(partie.sequence)
        pays_list = get_pays(partie.config.langue)
        pays_exact = next((p for p in pays_list if p["nom_normalise"] == seq_norm), None)
        pays_plus_long = any(
            p["nom_normalise"] != seq_norm
            and p["nom_normalise"].startswith(seq_norm)
            and p["nom_normalise"] not in partie.pays_joues_noms
            for p in pays_list
        )
        if pays_exact and pays_plus_long:
            snap["sequence_est_pays"] = True
            snap["sequence_pays_nom"] = pays_exact["nom"]

    await manager.diffuser(partie.room_id, snap)

    partie.chrono_task = asyncio.create_task(partie.lancer_chrono())

    if partie.joueurs[partie.joueur_actuel_id].est_ia:
        asyncio.create_task(ia_jouer(partie))


async def appliquer_perte_vie_externe(partie: Partie, joueur_id: str, raison: str):
    await partie.appliquer_perte_vie(joueur_id, raison)


async def traiter_lettre(partie: Partie, joueur_id: str, lettre: str):
    if partie.etat != EtatPartie.EN_COURS:
        return
    if joueur_id != partie.joueur_actuel_id:
        await manager.envoyer(partie.room_id, joueur_id, {"type": "erreur", "message": "Ce n'est pas ton tour !"})
        return
    partie.tours_sans_jouer[joueur_id] = 0  # a joué → reset AFK
    # FIX-LAC : guard en_attente_langue_au_chat supprimé — le jeu continue en parallèle

    nouvelle_seq = partie.sequence + normaliser(lettre)
    possibilites = chercher_pays(nouvelle_seq, partie.config.langue, partie.config.mode_mixte)

    if not possibilites:
        import time
        partie.sequence = nouvelle_seq
        partie.joueur_fautif = joueur_id
        await manager.diffuser(partie.room_id, {
            **partie.snapshot(),
            "type": "sequence_invalide",
            "sequence": nouvelle_seq,
            "joueur_fautif": joueur_id,
            "message": f"« {nouvelle_seq} » ne commence aucun pays.",
        })
        partie.prochain_vivant()
        await demarrer_tour(partie, reset_sequence=False)
        return

    partie.sequence = nouvelle_seq
    partie.annuler_chrono()

    match = est_complet(nouvelle_seq, partie.config.langue, partie.config.mode_mixte, partie.pays_joues_noms)

    if match:
        cle = match["nom_normalise"]
        if cle in partie.pays_joues_noms:
            await appliquer_perte_vie_externe(partie, joueur_id, f"🔁 {match['nom']} a déjà été joué !")
            return

        partie.pays_joues.append(match)
        partie.pays_joues_noms.add(cle)

        await manager.diffuser(partie.room_id, {
            **partie.snapshot(),
            "type": "mot_complet",
            "pays": match,
            "joueur_fautif": joueur_id,
            "message": f"💀 {partie.joueurs[joueur_id].nom} a complété « {match['nom']} » et perd une vie !",
        })
        await asyncio.sleep(1.5)
        await appliquer_perte_vie_externe(partie, joueur_id, "Mot complet")
    else:
        partie.prochain_vivant()
        await demarrer_tour(partie, reset_sequence=False)


async def traiter_langue_au_chat(partie: Partie, demandeur_id: str):
    if partie.etat != EtatPartie.EN_COURS:
        return
    if demandeur_id != partie.joueur_actuel_id:
        await manager.envoyer(partie.room_id, demandeur_id, {"type": "erreur", "message": "Ce n'est pas ton tour !"})
        return
    if not partie.sequence:
        await manager.envoyer(partie.room_id, demandeur_id, {"type": "erreur", "message": "Aucune séquence en cours !"})
        return

    if partie.joueur_fautif and partie.joueur_fautif in partie.joueurs:
        interpelle_id = partie.joueur_fautif
    else:
        idx_precedent = (partie.index_tour - 1) % len(partie.ordre)
        interpelle_id = partie.ordre[idx_precedent]

    partie.en_attente_langue_au_chat = True
    partie.joueur_interpelle = interpelle_id
    partie.annuler_chrono()

    DELAI = 20

    await manager.diffuser(partie.room_id, {
        **partie.snapshot(),
        "type": "langue_au_chat",
        "demandeur": demandeur_id,
        "interpelle": interpelle_id,
        "delai": DELAI,
        "message": f"🗣️ {partie.joueurs[demandeur_id].nom} demande une langue au chat ! {partie.joueurs[interpelle_id].nom}, tu as {DELAI}s !",
    })

    if partie.lac_timeout_task and not partie.lac_timeout_task.done():
        partie.lac_timeout_task.cancel()

    if partie.joueurs[interpelle_id].est_ia:
        asyncio.create_task(_ia_repondre_langue_au_chat(partie, interpelle_id))
    else:
        partie.lac_timeout_task = asyncio.create_task(
            _timeout_langue_au_chat(partie, interpelle_id, DELAI)
        )


async def _timeout_langue_au_chat(partie: Partie, interpelle_id: str, delai: int):
    try:
        await asyncio.sleep(delai)
        if not partie.en_attente_langue_au_chat or partie.joueur_interpelle != interpelle_id:
            return
        if partie.etat != EtatPartie.EN_COURS:
            return

        partie.en_attente_langue_au_chat = False
        partie.joueur_interpelle = None

        joueur = partie.joueurs.get(interpelle_id)
        if not joueur:
            return

        joueur.vies -= 1
        if joueur.vies <= 0:
            joueur.vies = 0
            joueur.en_vie = False

        await manager.diffuser(partie.room_id, {
            **partie.snapshot(),
            "type": "perte_vie",
            "joueur_id": interpelle_id,
            "raison": "Timeout langue au chat",
            "vies_restantes": joueur.vies,
            "elimine": not joueur.en_vie,
            "message": f"⏰ {joueur.nom} n'a pas répondu ! ({joueur.vies} vie(s) restante(s))",
        })

        vivants = partie.joueurs_vivants
        if len(vivants) <= 1:
            await fin_de_partie(partie, vivants[0] if vivants else None)
            return

        await asyncio.sleep(0.8)
        if interpelle_id in partie.ordre and joueur.en_vie:
            partie.index_tour = partie.ordre.index(interpelle_id)
        else:
            partie.prochain_vivant()
        await demarrer_tour(partie)
    except asyncio.CancelledError:
        pass


async def _ia_repondre_langue_au_chat(partie: Partie, ia_id: str):
    await asyncio.sleep(random.uniform(1.5, 3.0))
    if not partie.en_attente_langue_au_chat or partie.joueur_interpelle != ia_id:
        return

    seq_norm = normaliser(partie.sequence)
    pays_list = get_pays(partie.config.langue)
    candidats = [
        p for p in pays_list
        if p["nom_normalise"].startswith(seq_norm)
        and p["nom_normalise"] not in partie.pays_joues_noms
    ]

    if candidats:
        pays = random.choice(candidats)
        valeur = pays["nom"]
        await traiter_reponse_langue_au_chat(partie, ia_id, valeur)
    else:
        await traiter_reponse_langue_au_chat(partie, ia_id, "___RIEN___")


async def traiter_reponse_langue_au_chat(partie: Partie, joueur_id: str, pays_propose: str):
    if not partie.en_attente_langue_au_chat:
        return
    if joueur_id != partie.joueur_interpelle:
        await manager.envoyer(partie.room_id, joueur_id, {"type": "erreur", "message": "Tu n'es pas interpellé !"})
        return

    # Annuler timeout
    if partie.lac_timeout_task and not partie.lac_timeout_task.done():
        partie.lac_timeout_task.cancel()
        partie.lac_timeout_task = None

    # Débloquer
    partie.en_attente_langue_au_chat = False
        
    nom_norm = normaliser(pays_propose)
    pays_list = get_pays(partie.config.langue)
    match = next((p for p in pays_list if p["nom_normalise"] == nom_norm), None)
    if match is None and partie.config.mode_mixte:
        match = next((p for p in pays_list if p.get("capitale_normalisee") == nom_norm), None)

    seq_norm = normaliser(partie.sequence)
    demandeur_id = partie.joueur_actuel_id

    if match is None:
        await manager.diffuser(partie.room_id, {
            **partie.snapshot(),
            "type": "verdict_langue_au_chat",
            "valide": False,
            "message": f"❌ « {pays_propose} » n'existe pas ! {partie.joueurs[joueur_id].nom} perd une vie.",
        })
        await asyncio.sleep(1.5)
        await appliquer_perte_vie_externe(partie, joueur_id, "Pays inexistant")

    elif match["nom_normalise"] in partie.pays_joues_noms:
        await manager.diffuser(partie.room_id, {
            **partie.snapshot(),
            "type": "verdict_langue_au_chat",
            "valide": False,
            "message": f"🔁 {match['nom']} déjà joué ! {partie.joueurs[joueur_id].nom} perd une vie.",
        })
        await asyncio.sleep(1.5)
        await appliquer_perte_vie_externe(partie, joueur_id, "Pays déjà joué")

    elif not match["nom_normalise"].startswith(seq_norm):
        await manager.diffuser(partie.room_id, {
            **partie.snapshot(),
            "type": "verdict_langue_au_chat",
            "valide": False,
            "message": f"⚠️ {match['nom']} ne commence pas par « {partie.sequence} » !",
        })
        await asyncio.sleep(1.5)
        await appliquer_perte_vie_externe(partie, joueur_id, "Séquence incorrecte")

    else:
        partie.pays_joues.append(match)
        partie.pays_joues_noms.add(match["nom_normalise"])
        await manager.diffuser(partie.room_id, {
            **partie.snapshot(),
            "type": "verdict_langue_au_chat",
            "valide": True,
            "pays": match,
            "message": f"✅ {match['nom']} est valide ! {partie.joueurs[demandeur_id].nom} perd une vie.",
        })
        await asyncio.sleep(1.5)
        await appliquer_perte_vie_externe(partie, demandeur_id, "Langue au chat perdue")


async def fin_de_partie(partie: Partie, gagnant_id: Optional[str]):
    partie.etat = EtatPartie.TERMINEE
    partie.annuler_chrono()
    gagnant_nom = partie.joueurs[gagnant_id].nom if gagnant_id and gagnant_id in partie.joueurs else "Personne"
    await manager.diffuser(partie.room_id, {
        **partie.snapshot(),
        "type": "fin_partie",
        "gagnant": gagnant_id,
        "message": f"🏆 {gagnant_nom} remporte la partie !",
    })

# ──────────────────────────────────────────────────────────────
#  IA
# ──────────────────────────────────────────────────────────────

async def traiter_stopper_sequence(partie: Partie, joueur_id: str):
    """Le joueur actuel stoppe : l'auteur de la dernière lettre a complété un pays → il perd une vie."""
    if partie.etat != EtatPartie.EN_COURS:
        return
    if joueur_id != partie.joueur_actuel_id:
        await manager.envoyer(partie.room_id, joueur_id, {"type": "erreur", "message": "Ce n'est pas ton tour !"})
        return
    seq_norm = normaliser(partie.sequence)
    pays_exact = next((p for p in get_pays(partie.config.langue) if p["nom_normalise"] == seq_norm), None)
    if not pays_exact:
        await manager.envoyer(partie.room_id, joueur_id, {"type": "erreur", "message": "La séquence ne forme pas un pays !"})
        return
    fautif_id = partie.joueur_fautif if partie.joueur_fautif and partie.joueur_fautif in partie.joueurs else joueur_id
    if pays_exact["nom_normalise"] not in partie.pays_joues_noms:
        partie.pays_joues.append(pays_exact)
        partie.pays_joues_noms.add(pays_exact["nom_normalise"])
    await manager.diffuser(partie.room_id, {
        **partie.snapshot(),
        "type": "mot_complet",
        "pays": pays_exact,
        "joueur_fautif": fautif_id,
        "message": f"🛑 {partie.joueurs[joueur_id].nom} stoppe ! « {pays_exact['nom']} » — {partie.joueurs[fautif_id].nom} perd une vie.",
    })
    await asyncio.sleep(1.5)
    await appliquer_perte_vie_externe(partie, fautif_id, f"Séquence stoppée sur {pays_exact['nom']}")


async def ia_jouer(partie: Partie):
    await asyncio.sleep(random.uniform(1.2, 2.8))

    if partie.etat != EtatPartie.EN_COURS:
        return
    if not partie.joueurs.get(partie.joueur_actuel_id, EtatJoueur(id="", nom="", vies=0)).est_ia:
        return

    seq_norm = normaliser(partie.sequence)
    possibilites = chercher_pays(seq_norm, partie.config.langue, partie.config.mode_mixte)
    non_joues = [p for p in possibilites if p["nom_normalise"] not in partie.pays_joues_noms]

    if not non_joues:
        if partie.joueur_fautif and partie.joueur_fautif != partie.joueur_actuel_id:
            await traiter_langue_au_chat(partie, partie.joueur_actuel_id)
        else:
            await partie.appliquer_perte_vie(partie.joueur_actuel_id, "IA piégée")
        return

    cibles = [p for p in non_joues if len(p["nom_normalise"]) > len(seq_norm) + 1]
    if not cibles:
        cibles = non_joues

    pays_cible = random.choice(cibles)
    nom_cible = pays_cible["nom_normalise"]
    lettre_suivante = nom_cible[len(seq_norm)]
    await traiter_lettre(partie, partie.joueur_actuel_id, lettre_suivante)

# ──────────────────────────────────────────────────────────────
#  ROUTES HTTP
# ──────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "message": "Pays Game Server 🌍"}

@app.get("/parties")
async def lister_parties():
    return [
        {
            "room_id": p.room_id,
            "etat": p.etat.value,
            "joueurs": len(p.joueurs),
            "max_joueurs": p.config.max_joueurs,
            "langue": p.config.langue,
        }
        for p in parties.values()
        if p.etat == EtatPartie.ATTENTE
    ]

@app.post("/parties")
async def creer_partie(config: Config):
    room_id = generer_room_id()
    while room_id in parties:
        room_id = generer_room_id()
    parties[room_id] = Partie(room_id, config, createur_id="")
    return {"room_id": room_id, "lien": f"/rejoindre/{room_id}"}

@app.get("/parties/{room_id}")
async def info_partie(room_id: str):
    if room_id not in parties:
        raise HTTPException(status_code=404, detail="Partie introuvable")
    return parties[room_id].snapshot()

@app.post("/parties/{room_id}/demarrer")
async def demarrer_partie(room_id: str, joueur_id: str):
    if room_id not in parties:
        raise HTTPException(status_code=404, detail="Partie introuvable")
    partie = parties[room_id]
    if partie.etat != EtatPartie.ATTENTE:
        raise HTTPException(status_code=400, detail="Partie déjà démarrée")
    if len(partie.joueurs) < 1:
        raise HTTPException(status_code=400, detail="Pas assez de joueurs")

    partie.etat = EtatPartie.EN_COURS
    partie.ordre = list(partie.joueurs.keys())
    random.shuffle(partie.ordre)
    partie.index_tour = 0

    await manager.diffuser(room_id, {
        **partie.snapshot(),
        "type": "partie_demarree",
        "message": "🎮 La partie commence !",
    })
    await demarrer_tour(partie)
    return {"status": "ok"}

@app.post("/parties/{room_id}/ia")
async def ajouter_ia(room_id: str):
    if room_id not in parties:
        raise HTTPException(status_code=404, detail="Partie introuvable")
    partie = parties[room_id]
    ia_id = f"ia_{random.randint(1000, 9999)}"
    partie.joueurs[ia_id] = EtatJoueur(
        id=ia_id, nom="🤖 Ordinateur", vies=partie.config.vies, est_ia=True
    )
    await manager.diffuser(room_id, {
        **partie.snapshot(),
        "type": "joueur_rejoint",
        "message": "🤖 L'ordinateur a rejoint la partie !",
    })
    return {"ia_id": ia_id}

# ──────────────────────────────────────────────────────────────
#  WEBSOCKET PRINCIPAL
# ──────────────────────────────────────────────────────────────

@app.websocket("/ws/{room_id}/{joueur_id}/{nom}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, joueur_id: str, nom: str):
    from urllib.parse import unquote
    joueur_id = unquote(joueur_id)
    nom       = unquote(nom)

    # Créer la room si elle n'existe pas (rejoindre via lien direct)
    if room_id not in parties:
        parties[room_id] = Partie(room_id, Config(), createur_id=joueur_id)

    partie = parties[room_id]

    # Bloquer si partie déjà en cours et joueur inconnu
    if joueur_id not in partie.joueurs:
        if partie.etat == EtatPartie.EN_COURS:
            await websocket.close(code=4001, reason="Partie deja en cours")
            return
        if len(partie.joueurs) >= partie.config.max_joueurs:
            await websocket.close(code=4002, reason="Partie pleine")
            return
        partie.joueurs[joueur_id] = EtatJoueur(
            id=joueur_id,
            nom=nom or f"Joueur{len(partie.joueurs)+1}",
            vies=partie.config.vies,
        )

    await manager.connecter(room_id, joueur_id, websocket)

    # Informer tout le monde
    await manager.diffuser(room_id, {
        **partie.snapshot(),
        "type": "joueur_rejoint",
        "joueur_id": joueur_id,
        "message": f"👋 {partie.joueurs[joueur_id].nom} a rejoint !",
    })

    # Reconnexion en cours de partie : envoyer l'état actuel
    if partie.etat == EtatPartie.EN_COURS:
        await manager.envoyer(room_id, joueur_id, {
            **partie.snapshot(),
            "type": "partie_demarree",
            "message": "🎮 Synchronisation…",
        })

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "")

            if action == "lettre":
                await traiter_lettre(partie, joueur_id, data.get("lettre", ""))

            elif action == "langue_au_chat":
                await traiter_langue_au_chat(partie, joueur_id)

            elif action == "reponse_langue_au_chat":
                await traiter_reponse_langue_au_chat(partie, joueur_id, data.get("pays", ""))

            elif action == "stopper_sequence":
                await traiter_stopper_sequence(partie, joueur_id)

            elif action == "chat":
                texte = str(data.get("texte", ""))[:200]
                await manager.diffuser(room_id, {
                    "type": "chat",
                    "joueur_id": joueur_id,
                    "nom": partie.joueurs[joueur_id].nom,
                    "texte": texte,
                    "heure": datetime.now().strftime("%H:%M"),
                })

            elif action == "ping":
                await manager.envoyer(room_id, joueur_id, {"type": "pong"})

    except WebSocketDisconnect:
        manager.deconnecter(room_id, joueur_id)

        if joueur_id in partie.joueurs:
            await manager.diffuser(room_id, {
                **partie.snapshot(),
                "type": "joueur_parti",
                "joueur_id": joueur_id,
                "message": f"⚠️ {partie.joueurs[joueur_id].nom} s'est déconnecté(e).",
            })

            if partie.etat == EtatPartie.EN_COURS:
                # Joueur interpellé (langue au chat) se déconnecte
                if partie.en_attente_langue_au_chat and partie.joueur_interpelle == joueur_id:
                    if partie.lac_timeout_task and not partie.lac_timeout_task.done():
                        partie.lac_timeout_task.cancel()
                        partie.lac_timeout_task = None
                    partie.en_attente_langue_au_chat = False
                    partie.joueur_interpelle = None
                    await manager.diffuser(room_id, {
                        **partie.snapshot(),
                        "type": "verdict_langue_au_chat",
                        "valide": False,
                        "message": "🔌 Joueur déconnecté — langue au chat annulée.",
                    })
                    await asyncio.sleep(1.0)
                    await appliquer_perte_vie_externe(partie, joueur_id, "Déconnexion pendant langue au chat")

                # C'était son tour
                elif partie.joueur_actuel_id == joueur_id:
                    partie.annuler_chrono()
                    partie.prochain_vivant()
                    await demarrer_tour(partie, reset_sequence=False)

# ──────────────────────────────────────────────────────────────
#  NETTOYAGE PÉRIODIQUE
# ──────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    asyncio.create_task(nettoyer_parties())

async def nettoyer_parties():
    while True:
        await asyncio.sleep(3600)
        terminees = [rid for rid, p in parties.items() if p.etat == EtatPartie.TERMINEE]
        for rid in terminees:
            del parties[rid]
