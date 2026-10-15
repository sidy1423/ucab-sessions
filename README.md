# Système de Documentation des Séances Universitaires

**Université Cheikh Ahmadou Bamba (UCAB)**
Faculté des sciences religieuses, humaines et civilisations
République du Sénégal

---

## Description

Application web multi-utilisateurs pour la documentation des séances
d'enseignement universitaires.

**Langues supportées** : Français (par défaut), العربية (RTL)

---

## Rôles

| Rôle | Description |
|------|-------------|
| Enseignant | Documente ses séances |
| Secrétaire | Crée les affectations |
| Directeur des études | Approuve/rejette les séances |
| Doyen | Vue globale (lecture seule) |
| Comptable | Consulte les heures |
| Administrateur | Tous les droits + suppression |

---

## Règles métier

1. Jours d'étude : Lundi → Samedi
2. Durée d'une séance : 2 heures
3. Workflow : Brouillon → En attente → Approuvée / Rejetée
4. Verrouillage 24h après la fin de la séance
5. Heures comptées : seules les séances approuvées
6. Suppression : réservée au superuser

---

## Installation (Windows)

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## Tests

```powershell
python manage.py test academics -v 2
```

34 tests couvrent : création, workflow, verrouillage 24h,
calcul des heures, permissions.

---

## Comptes de test

| Username | Mot de passe | Rôle |
|----------|--------------|------|
| admin | Admin2026 | Superuser |
| director1 | Test1234 | Directeur |
| secretary1 | Test1234 | Secrétaire |
| dean1 | Test1234 | Doyen |
| teacher1 | Test1234 | Enseignant |
| accountant1 | Test1234 | Comptable |

---

## Production

Voir config/settings_production.py

Checklist :
- [ ] DEBUG=False
- [ ] SECRET_KEY forte
- [ ] ALLOWED_HOSTS configuré
- [ ] PostgreSQL
- [ ] collectstatic
- [ ] gunicorn/waitress + nginx
- [ ] SSL (Let's Encrypt)

---

Propriété de l'Université Cheikh Ahmadou Bamba (UCAB).
