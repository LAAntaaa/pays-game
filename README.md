# 🌍 PAYS GAME — Guide complet

## Structure du projet

```
pays-game/
│
├── server.py          ← Backend FastAPI + WebSockets
├── requirements.txt   ← Dépendances serveur
│
├── pays_fr.json       ← 192 pays en français
├── pays_en.json       ← 192 pays en anglais
│
├── index.html         ← Interface web (ouvrir dans navigateur)
│
├── main.py            ← Client Kivy (mobile/desktop)
├── buildozer.spec     ← Config build Android
│
└── README.md
```

---

## 🚀 Lancement rapide — Mode Solo (sans serveur)

### Web
Ouvrir `index.html` directement dans un navigateur.
→ Le jeu détecte l'absence de serveur et bascule en mode solo vs IA.

### Kivy
```bash
pip install kivy websockets
python main.py
```
→ Même logique : si le serveur est absent, solo vs IA automatiquement.

---

## 🌐 Lancement avec serveur (multijoueur en ligne)

### 1. Lancer le serveur
```bash
pip install fastapi uvicorn[standard] websockets python-multipart
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Adapter l'URL dans les clients

**index.html** — ligne ~620 :
```javascript
const SERVEUR_HTTP = 'http://localhost:8000';   // dev local
// const SERVEUR_HTTP = 'https://ton-app.onrender.com';  // prod
```

**main.py** — ligne ~46 :
```python
SERVEUR_WS   = "ws://localhost:8000"
SERVEUR_HTTP = "http://localhost:8000"
```

### 3. Créer une partie et inviter des amis
1. Ouvrir `index.html` → Créer une partie
2. Le code à 6 lettres s'affiche dans le lobby
3. Partager le lien `https://ton-serveur/?room=ABCDEF`
4. Les amis ouvrent le lien → ils rejoignent automatiquement

---

## ☁️ Déploiement gratuit (Render.com)

1. Push le projet sur GitHub
2. Sur [render.com](https://render.com) → New Web Service
3. **Build Command** : `pip install -r requirements.txt`
4. **Start Command** : `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. Mettre l'URL Render dans `index.html` et `main.py`

---

## 📱 Build Android (Buildozer)

```bash
pip install buildozer
# Sur Linux/Mac uniquement
buildozer android debug
# L'APK sera dans bin/
```

---

## 🎮 Règles du jeu

| Situation | Résultat |
|-----------|----------|
| Tu poses la dernière lettre d'un pays | ❤️ Tu perds une vie |
| Tu entres une séquence qui ne commence aucun pays | Le joueur suivant peut demander une langue au chat |
| Langue au chat demandée → tu révèles ton pays et il est valide | ❤️ Le demandeur perd une vie |
| Langue au chat → ton pays n'existe pas | ❤️ Tu perds une vie |
| Langue au chat → ton pays a déjà été joué | ❤️ Tu perds une vie |
| Le chrono tombe à 0 | ❤️ Tu perds une vie |
| Plus de vies | 💀 Éliminé |
| Dernier survivant | 🏆 Victoire |

---

## 🗺️ Base de données pays

- **192 pays** reconnus par l'ONU
- Champs : `nom`, `capitale`, `code` (ISO2), `nom_normalise`, `capitale_normalisee`
- Les champs `_normalise` permettent la saisie sans accents (EGYPTE = ÉGYPTE)
- Drapeaux via [flagcdn.com](https://flagcdn.com) (CDN gratuit)
