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
║                                                              ║
║  Hébergement gratuit : Railway, Render, Fly.io               ║
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

app = FastAPI(title="Pays Game API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # En prod, restreindre à ton domaine
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────
#  DONNÉES PAYS
# ──────────────────────────────────────────────────────────────

def charger_pays(langue: str) -> List[dict]:
    fichier = f"pays_{langue}.json"
    try:
        with open(fichier, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback minimal si le fichier est absent
        return [{"nom": "FRANCE", "capitale": "PARIS", "code": "fr", "nom_normalise": "FRANCE", "capitale_normalisee": "PARIS"}]

PAYS_FR = charger_pays("fr")
PAYS_EN = charger_pays("en")

def get_pays(langue: str) -> List[dict]:
    return PAYS_FR if langue == "fr" else PAYS_EN

def normaliser(s: str) -> str:
    """Supprime accents, espaces et tirets — cohérent avec le clavier du joueur."""
    s = unicodedata.normalize("NFD", s.upper()).encode("ascii", "ignore").decode("ascii")
    return s.replace(" ", "").replace("-", "").replace("'", "")

def chercher_pays(sequence: str, langue: str, mode_mixte: bool) -> List[dict]:
    """Retourne tous les pays/capitales dont le nom commence par `sequence`."""
    seq = normaliser(sequence)
    pays = get_pays(langue)
    resultats = []
    for p in pays:
        if p["nom_normalise"].startswith(seq):
            resultats.append({"type": "pays", **p})
        elif mode_mixte and p["capitale_normalisee"].startswith(seq):
            resultats.append({"type": "capitale", **p})
    return resultats

def est_complet(sequence: str, langue: str, mode_mixte: bool) -> Optional[dict]:
    """Retourne le pays si la séquence forme un nom complet exact."""
    seq = normaliser(sequence)
    for p in get_pays(langue):
        if p["nom_normalise"] == seq:
            return {**p, "type": "pays"}
        if mode_mixte and p["capitale_normalisee"] == seq:
            return {**p, "type": "capitale"}
    return None

# ──────────────────────────────────────────────────────────────
#  MODÈLES
# ──────────────────────────────────────────────────────────────

class Config(BaseModel):
    langue: str = "fr"          # "fr" | "en"
    mode_mixte: bool = False    # pays + capitales
    vies: int = 10              # vies de départ
    temps: int = 15             # secondes par tour
    max_joueurs: int = 8

class EtatJoueur(BaseModel):
    id: str
    nom: str
    vies: int
    en_vie: bool = True
    est_ia: bool = False

class EtatPartie(str, Enum):
    ATTENTE    = "attente"      # lobby, on attend des joueurs
    EN_COURS   = "en_cours"     # partie lancée
    TERMINEE   = "terminee"     # fin de partie

# ──────────────────────────────────────────────────────────────
#  GESTIONNAIRE DE CONNEXIONS
# ──────────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        # room_id → {joueur_id: WebSocket}
        self.actifs: Dict[str, Dict[str, WebSocket]] = {}

    async def connecter(self, room_id: str, joueur_id: str, ws: WebSocket):
        await ws.accept()
        if room_id not in self.actifs:
            self.actifs[room_id] = {}
        self.actifs[room_id][joueur_id] = ws

    def deconnecter(self, room_id: str, joueur_id: str):
        if room_id in self.actifs:
            self.actifs[room_id].pop(joueur_id, None)

    async def envoyer(self, room_id: str, joueur_id: str, message: dict):
        ws = self.actifs.get(room_id, {}).get(joueur_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def diffuser(self, room_id: str, message: dict, exclure: str = None):
        """Envoie à tous les joueurs de la room (sauf `exclure`)."""
        for jid, ws in list(self.actifs.get(room_id, {}).items()):
            if jid == exclure:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# ──────────────────────────────────────────────────────────────
#  ÉTAT DES PARTIES
# ──────────────────────────────────────────────────────────────

class Partie:
    def __init__(self, room_id: str, config: Config, createur_id: str):
        self.room_id       = room_id
        self.config        = config
        self.createur_id   = createur_id
        self.etat          = EtatPartie.ATTENTE
        self.joueurs: Dict[str, EtatJoueur] = {}
        self.ordre: List[str] = []          # ordre de jeu (ids)
        self.index_tour    = 0              # qui joue en ce moment
        self.sequence      = ""            # lettres posées ce tour
        self.pays_joues: List[dict] = []   # historique des pays complétés
        self.pays_joues_noms: Set[str] = set()  # pour vérif doublons rapides
        self.en_attente_langue_au_chat = False  # flag langue au chat
        self.joueur_interpelle: Optional[str] = None  # qui doit répondre
        self.joueur_fautif: Optional[str] = None       # qui a posé la séquence en cours
        self.chrono_task: Optional[asyncio.Task] = None

    # ── Propriétés utiles ──────────────────────────────────────

    @property
    def joueur_actuel_id(self) -> Optional[str]:
        if not self.ordre:
            return None
        return self.ordre[self.index_tour % len(self.ordre)]

    @property
    def joueurs_vivants(self) -> List[str]:
        return [jid for jid, j in self.joueurs.items() if j.en_vie and not j.est_ia]

    def prochain_vivant(self) -> str:
        """Passe à l'index suivant en sautant les joueurs éliminés."""
        n = len(self.ordre)
        for _ in range(n):
            self.index_tour = (self.index_tour + 1) % n
            jid = self.ordre[self.index_tour]
            if self.joueurs[jid].en_vie:
                return jid
        return self.joueur_actuel_id

    # ── Snapshot envoyé aux clients ────────────────────────────

    def snapshot(self) -> dict:
        return {
            "type": "etat",
            "room_id": self.room_id,
            "etat": self.etat.value,
            "config": self.config.model_dump() if hasattr(self.config, "model_dump") else self.config.dict(),
            "joueurs": [j.model_dump() if hasattr(j, "model_dump") else j.dict() for j in self.joueurs.values()],
            "ordre": self.ordre,
            "joueur_actuel": self.joueur_actuel_id,
            "sequence": self.sequence,
            "pays_joues": self.pays_joues,
            "en_attente_langue_au_chat": self.en_attente_langue_au_chat,
            "joueur_interpelle": self.joueur_interpelle,
            "joueur_fautif": self.joueur_fautif,
        }

    # ── Chrono ─────────────────────────────────────────────────

    def annuler_chrono(self):
        if self.chrono_task and not self.chrono_task.done():
            self.chrono_task.cancel()

    async def lancer_chrono(self):
        """Chrono asynchrone — expire → perd une vie."""
        try:
            await asyncio.sleep(self.config.temps)
            # Temps écoulé
            jid = self.joueur_actuel_id
            await self.appliquer_perte_vie(jid, "⏰ Temps écoulé !")
        except asyncio.CancelledError:
            pass  # Chrono annulé normalement

# ──────────────────────────────────────────────────────────────
#  REGISTRE GLOBAL DES PARTIES
# ──────────────────────────────────────────────────────────────

parties: Dict[str, Partie] = {}

def generer_room_id() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=6))

# ──────────────────────────────────────────────────────────────
#  LOGIQUE DE JEU (méthodes sur Partie)
# ──────────────────────────────────────────────────────────────

async def demarrer_tour(partie: Partie, reset_sequence: bool = True):
    """Initialise un nouveau tour et lance le chrono.
    reset_sequence=False : conserver la séquence (simple passage de tour).
    reset_sequence=True  : nouveau round après perte de vie.
    """
    if reset_sequence:
        partie.sequence = ""
        partie.joueur_fautif = None
    partie.en_attente_langue_au_chat = False
    partie.joueur_interpelle = None
    partie.annuler_chrono()

    await manager.diffuser(partie.room_id, {
        **partie.snapshot(),
        "type": "nouveau_tour",
        "message": f"Tour de {partie.joueurs[partie.joueur_actuel_id].nom}",
    })

    partie.chrono_task = asyncio.create_task(partie.lancer_chrono())

    # Si c'est le tour de l'IA, on la fait jouer après un délai
    if partie.joueurs[partie.joueur_actuel_id].est_ia:
        asyncio.create_task(ia_jouer(partie))


async def traiter_lettre(partie: Partie, joueur_id: str, lettre: str):
    """Un joueur ajoute une lettre."""
    if partie.etat != EtatPartie.EN_COURS:
        return
    if joueur_id != partie.joueur_actuel_id:
        await manager.envoyer(partie.room_id, joueur_id, {"type": "erreur", "message": "Ce n'est pas ton tour !"})
        return
    if partie.en_attente_langue_au_chat:
        await manager.envoyer(partie.room_id, joueur_id, {"type": "erreur", "message": "En attente de réponse langue au chat."})
        return

    nouvelle_seq = normaliser(partie.sequence) + normaliser(lettre)
    possibilites = chercher_pays(nouvelle_seq, partie.config.langue, partie.config.mode_mixte)

    if not possibilites:
        # Séquence invalide → stocker le fautif, passer au suivant SANS reset
        partie.sequence = nouvelle_seq
        partie.joueur_fautif = joueur_id
        await manager.diffuser(partie.room_id, {
            **partie.snapshot(),
            "type": "sequence_invalide",
            "sequence": nouvelle_seq,
            "joueur_fautif": joueur_id,
            "message": f"⚠️ « {nouvelle_seq} » ne commence aucun pays ! Le joueur suivant peut demander une langue au chat.",
        })
        partie.prochain_vivant()
        # Conserver la séquence pour que l'IA/adversaire puisse demander langue au chat
        await demarrer_tour(partie, reset_sequence=False)
        return

    # Séquence valide
    partie.sequence = nouvelle_seq
    partie.annuler_chrono()

    # Mot complet ?
    match = est_complet(nouvelle_seq, partie.config.langue, partie.config.mode_mixte)

    if match:
        # Vérifie si déjà joué
        cle = match["nom_normalise"]
        if cle in partie.pays_joues_noms:
            # Pays déjà joué → perte de vie immédiate
            await appliquer_perte_vie_externe(partie, joueur_id, f"🔁 {match['nom']} a déjà été joué !")
            return

        # Celui qui complète le mot perd une vie
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
        # Tour suivant — conserver la séquence (l'adversaire continue)
        partie.joueur_fautif = joueur_id
        partie.prochain_vivant()
        await demarrer_tour(partie, reset_sequence=False)


async def traiter_langue_au_chat(partie: Partie, demandeur_id: str):
    """
    Le joueur actuel pense que la séquence est invalide et demande une explication.
    → Le joueur PRÉCÉDENT doit révéler son pays.
    """
    if partie.etat != EtatPartie.EN_COURS:
        return
    if demandeur_id != partie.joueur_actuel_id:
        await manager.envoyer(partie.room_id, demandeur_id, {"type": "erreur", "message": "Ce n'est pas ton tour !"})
        return

    # Le joueur précédent dans l'ordre
    idx_precedent = (partie.index_tour - 1) % len(partie.ordre)
    interpelle_id = partie.ordre[idx_precedent]

    partie.en_attente_langue_au_chat = True
    partie.joueur_interpelle = interpelle_id
    partie.annuler_chrono()

    await manager.diffuser(partie.room_id, {
        **partie.snapshot(),
        "type": "langue_au_chat",
        "demandeur": demandeur_id,
        "interpelle": interpelle_id,
        "message": f"🗣️ {partie.joueurs[demandeur_id].nom} demande une langue au chat ! {partie.joueurs[interpelle_id].nom}, quel pays visais-tu ?",
    })


async def traiter_reponse_langue_au_chat(partie: Partie, joueur_id: str, pays_propose: str):
    """Le joueur interpellé révèle son pays."""
    if not partie.en_attente_langue_au_chat:
        return
    if joueur_id != partie.joueur_interpelle:
        await manager.envoyer(partie.room_id, joueur_id, {"type": "erreur", "message": "Tu n'es pas interpellé !"})
        return

    nom_norm = normaliser(pays_propose)
    seq_norm = normaliser(partie.sequence)
    pays_list = get_pays(partie.config.langue)

    # Chercher dans les noms ET capitales (mode mixte)
    match = next((p for p in pays_list if p["nom_normalise"] == nom_norm), None)
    champ_match = "nom_normalise"
    valeur_affichee = pays_propose

    if not match and partie.config.mode_mixte:
        match = next((p for p in pays_list if p.get("capitale_normalisee") == nom_norm), None)
        if match:
            champ_match = "capitale_normalisee"
            valeur_affichee = match.get("capitale", pays_propose)

    if match is None:
        await manager.diffuser(partie.room_id, {
            "type": "verdict_langue_au_chat",
            "valide": False,
            "pays_propose": pays_propose,
            "interpelle": joueur_id,
            "message": f"❌ « {pays_propose} » n'existe pas ! {partie.joueurs[joueur_id].nom} perd une vie.",
        })
        await asyncio.sleep(1.5)
        await appliquer_perte_vie_externe(partie, joueur_id, "Pays inexistant")

    elif match["nom_normalise"] in partie.pays_joues_noms:
        await manager.diffuser(partie.room_id, {
            "type": "verdict_langue_au_chat",
            "valide": False,
            "pays_propose": pays_propose,
            "pays": match,
            "interpelle": joueur_id,
            "message": f"🔁 « {valeur_affichee} » a déjà été joué ! {partie.joueurs[joueur_id].nom} perd une vie.",
        })
        await asyncio.sleep(1.5)
        await appliquer_perte_vie_externe(partie, joueur_id, "Pays déjà joué")

    elif not match[champ_match].startswith(seq_norm):
        await manager.diffuser(partie.room_id, {
            "type": "verdict_langue_au_chat",
            "valide": False,
            "pays_propose": pays_propose,
            "pays": match,
            "interpelle": joueur_id,
            "message": f"⚠️ « {valeur_affichee} » ne commence pas par « {partie.sequence} » ! {partie.joueurs[joueur_id].nom} perd une vie.",
        })
        await asyncio.sleep(1.5)
        await appliquer_perte_vie_externe(partie, joueur_id, "Pays ne correspond pas à la séquence")

    else:
        # Valide → le DEMANDEUR perd une vie
        demandeur_id = partie.joueur_actuel_id
        partie.pays_joues.append({**match, "_valeur_jouee": valeur_affichee})
        partie.pays_joues_noms.add(match["nom_normalise"])

        await manager.diffuser(partie.room_id, {
            "type": "verdict_langue_au_chat",
            "valide": True,
            "pays_propose": pays_propose,
            "pays": match,
            "valeur_jouee": valeur_affichee,
            "interpelle": joueur_id,
            "demandeur": demandeur_id,
            "message": f"✅ « {valeur_affichee} » est valide ! C'est {partie.joueurs[demandeur_id].nom} qui perd une vie.",
        })
        await asyncio.sleep(1.5)
        await appliquer_perte_vie_externe(partie, demandeur_id, "Langue au chat perdue")


async def appliquer_perte_vie_externe(partie: Partie, joueur_id: str, raison: str):
    """Point centralisé pour retirer une vie et vérifier la fin de partie."""
    await partie.appliquer_perte_vie(joueur_id, raison)


# Rattacher la méthode à la classe
async def _appliquer_perte_vie(self: Partie, joueur_id: str, raison: str):
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
        "message": f"💔 {joueur.nom} perd une vie ! ({joueur.vies} restantes) — {raison}",
    })

    # Vérifier fin de partie
    vivants = self.joueurs_vivants
    if len(vivants) <= 1:
        await fin_de_partie(self, vivants[0] if vivants else None)
        return

    # Celui qui a perdu recommence (repart en premier sur la séquence vide)
    # On replace l'index sur ce joueur
    if joueur_id in self.ordre and joueur.en_vie:
        self.index_tour = self.ordre.index(joueur_id)
    else:
        self.prochain_vivant()

    await asyncio.sleep(0.5)
    # Après une perte de vie → toujours reset la séquence
    await demarrer_tour(self, reset_sequence=True)

Partie.appliquer_perte_vie = _appliquer_perte_vie


async def fin_de_partie(partie: Partie, gagnant_id: Optional[str]):
    partie.etat = EtatPartie.TERMINEE
    partie.annuler_chrono()

    gagnant_nom = partie.joueurs[gagnant_id].nom if gagnant_id else "Personne"
    await manager.diffuser(partie.room_id, {
        **partie.snapshot(),
        "type": "fin_partie",
        "gagnant": gagnant_id,
        "message": f"🏆 {gagnant_nom} remporte la partie !",
    })


# ──────────────────────────────────────────────────────────────
#  IA
# ──────────────────────────────────────────────────────────────

async def ia_jouer(partie: Partie):
    """L'IA choisit intelligemment sa lettre après un délai humain."""
    await asyncio.sleep(random.uniform(1.2, 2.8))

    if partie.etat != EtatPartie.EN_COURS:
        return
    if not partie.joueurs.get(partie.joueur_actuel_id, EtatJoueur(id="", nom="", vies=0)).est_ia:
        return

    seq_norm = normaliser(partie.sequence)
    possibilites = chercher_pays(seq_norm, partie.config.langue, partie.config.mode_mixte)

    # Filtrer les pays non encore joués
    non_joues = [p for p in possibilites if p["nom_normalise"] not in partie.pays_joues_noms]

    if not possibilites or not non_joues:
        # Séquence invalide OU tous pays joués
        if partie.joueur_fautif and partie.joueur_fautif != partie.joueur_actuel_id:
            # C'est le joueur humain qui a posé la séquence invalide → l'IA l'interpelle
            await traiter_langue_au_chat(partie, partie.joueur_actuel_id)
        else:
            # L'IA est piégée → elle donne sa langue au chat et perd une vie
            await manager.diffuser(partie.room_id, {
                "type": "ia_langue_au_chat",
                "message": "🤖 L'IA est piégée ! Elle perd une vie.",
            })
            await partie.appliquer_perte_vie(partie.joueur_actuel_id, "IA piégée")
        return

    # Stratégie : éviter de compléter si possible, parmi les pays non joués
    cibles = [p for p in non_joues if len(p["nom_normalise"] if p["type"] == "pays" else p["capitale_normalisee"]) > len(seq_norm) + 1]
    if not cibles:
        cibles = non_joues

    pays_cible = random.choice(cibles)
    nom_cible = pays_cible["nom_normalise"] if pays_cible["type"] == "pays" else pays_cible["capitale_normalisee"]
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
    """Liste les parties en attente (lobby public)."""
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
    """Crée une nouvelle partie, retourne le room_id et le lien de partage."""
    room_id = generer_room_id()
    while room_id in parties:
        room_id = generer_room_id()

    parties[room_id] = Partie(room_id, config, createur_id="")
    return {
        "room_id": room_id,
        "lien": f"/rejoindre/{room_id}",
        "message": "Partie créée ! Partagez le lien à vos amis.",
    }

@app.get("/parties/{room_id}")
async def info_partie(room_id: str):
    if room_id not in parties:
        raise HTTPException(status_code=404, detail="Partie introuvable")
    return parties[room_id].snapshot()

@app.post("/parties/{room_id}/demarrer")
async def demarrer_partie(room_id: str, joueur_id: str):
    """Le créateur lance la partie."""
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
    """Ajoute un joueur IA à la partie."""
    if room_id not in parties:
        raise HTTPException(status_code=404, detail="Partie introuvable")

    partie = parties[room_id]
    ia_id = f"ia_{random.randint(1000, 9999)}"
    partie.joueurs[ia_id] = EtatJoueur(
        id=ia_id,
        nom="🤖 Ordinateur",
        vies=partie.config.vies,
        est_ia=True,
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
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    joueur_id: str,
    nom: str,
):
    """
    Connexion WebSocket d'un joueur.

    Messages entrants (JSON) :
      { "action": "lettre",   "lettre": "F" }
      { "action": "langue_au_chat" }
      { "action": "reponse_langue_au_chat", "pays": "FRANCE" }
      { "action": "chat",     "texte": "Bonjour !" }
    """
    # Créer la room si elle n'existe pas encore (rejoindre via lien)
    if room_id not in parties:
        parties[room_id] = Partie(room_id, Config(), createur_id=joueur_id)

    partie = parties[room_id]

    # Ajouter le joueur s'il n'est pas déjà dedans
    if joueur_id not in partie.joueurs:
        if len(partie.joueurs) >= partie.config.max_joueurs:
            await websocket.close(code=1008, reason="Partie pleine")
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
        "message": f"👋 {partie.joueurs[joueur_id].nom} a rejoint la partie !",
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
        await manager.diffuser(room_id, {
            **partie.snapshot(),
            "type": "joueur_parti",
            "joueur_id": joueur_id,
            "message": f"👋 {partie.joueurs[joueur_id].nom} a quitté la partie.",
        })


# ──────────────────────────────────────────────────────────────
#  NETTOYAGE PÉRIODIQUE DES PARTIES TERMINÉES
# ──────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    asyncio.create_task(nettoyer_parties())

async def nettoyer_parties():
    while True:
        await asyncio.sleep(3600)  # toutes les heures
        terminees = [rid for rid, p in parties.items() if p.etat == EtatPartie.TERMINEE]
        for rid in terminees:
            del parties[rid]
