# Agent IA local pour migrer un conteneur Odoo 12 CE

## Lancement

Avec ce dépôt extrait sur le serveur Docker :

```sh
SOURCE_CONTAINER=odoo12 docker compose -f docker-compose.ai.yml up -d --build
```

Dans Dockhand, choisir `docker-compose.ai.yml` et définir seulement
`SOURCE_CONTAINER=odoo12`, puis déployer avec construction de l'image.
Dépôt : https://github.com/nallanot/odoo_migration_v2

La stack démarre trois services : Ollama, le téléchargement initial du modèle,
puis l'agent. Le modèle par défaut est `qwen3:8b`, exécuté localement sur CPU.
Aucune clé API ni intervention ChatGPT n'est nécessaire pendant le travail.
Le premier lancement télécharge le modèle et les images : il peut être long.
Prévoir de la RAM pour le modèle **en plus d'Odoo/PostgreSQL et des autres services**,
et assez de disque pour les modèles, images et copies intermédiaires. Les performances
sur CPU dépendent fortement de la machine. Aucun GPU n'est requis par ce Compose.

## Ce que fait réellement l'agent

1. Vérifie que le modèle répond et lit les compétences `.md`.
2. Inspecte le conteneur choisi, sa configuration standard et son réseau Docker.
3. Identifie PostgreSQL par l'hôte configuré et les alias sur un réseau partagé.
4. Identifie les bases Odoo 12 servies. Lorsque plusieurs bases sont possibles,
   il les traite séparément, sans deviner laquelle supprimer ou remplacer.
5. Résout `latest` depuis la définition officielle de l'image Docker Odoo, vérifie
   l'image et la branche officielle, puis fige la cible pour ce travail.
6. Sauvegarde chaque base et le filestore avec les modules d'origine. **Odoo est
   temporairement arrêté et redémarré pour chaque capture cohérente**. PostgreSQL source
   n'est pas supprimé. Des écritures externes directes en base nécessitent leur propre
   procédure de gel : l'agent ne les détecte pas toutes.
7. Migre sur des copies isolées avec le moteur existant. En cas d'erreur, l'IA lit
   les scripts, diagnostique et peut corriger un script de migration existant.
8. Exécute de nouveaux essais depuis le dernier checkpoint, sans désactiver les
   contrôles de données. Après réussite, teste une restauration puis exporte SQL + filestore.

L'IA intervient sur les blocages; les opérations ordinaires sont déterministes.
Son budget par base est limité à 16 actions par défaut. Trois décisions identiques
sans progrès interrompent la boucle. Les scripts avant/après et les raisons sont conservés.
Le contrôle syntaxique Python n'est pas une preuve de justesse métier : les essais
et comparaisons du moteur restent obligatoires.

## Compétences

La [documentation officielle OCA OpenUpgrade](https://oca.github.io/OpenUpgrade/)
est la référence principale pour la procédure, la couverture des modules, le diagnostic
et les vérifications après migration. Ses consignes sont synthétisées dans les compétences
20, 30 et 40 avec leurs liens et la date de consultation (2026-10-10). L'agent charge ces
synthèses; il ne consulte pas automatiquement le site Web. La couverture utilisée par le
moteur provient du checkout OpenUpgrade et reste liée au commit de chaque palier.
L'index documentaire consulté couvre jusqu'à 18→19 : cette source ne garantit pas 19→20.

Dans `odoo-migration-gui/skills/` :

- `00-agent.md` : mandat, format JSON, actions autorisées.
- `10-source-et-sauvegarde.md` : découverte et sauvegarde.
- `20-natif-et-openupgrade.md` : modules natifs, couverture et paliers.
- `30-diagnostic-et-reparation.md` : lecture, corrections limitées et reprise.
- `40-validation-et-livraison.md` : contrôles et conditions de réussite.

Ces fichiers sont réellement chargés dans le contexte du modèle et leurs empreintes
sont enregistrées dans `task.json`. Après modification, reconstruire l'image et
redéployer. Ils guident l'IA; ils ne lui donnent pas accès à des outils absents.
Les compétences sont embarquées dans l'image et les fichiers applicatifs sont en
lecture seule. Aucun éditeur de règles ou shell illimité n'est exposé au modèle.

## Résultats et suivi

```sh
docker compose -f docker-compose.ai.yml logs -f model-init agent
```

Dossier par défaut : `/opt/odoo-ai-migration`.

- `result.json` : résultat global, cible et état de chaque base.
- `task.json` : source identifiée, cible figée, modèle et empreintes des compétences.
- `jobs/<identifiant>/output/` : ZIP de sauvegarde finale, seulement après réussite.
- `jobs/<identifiant>/assistant.log` : opérations et erreurs.
- `jobs/<identifiant>/ai-history.json` : décisions du modèle.
- `jobs/<identifiant>/ai-patches/` : scripts avant/après.
- `jobs/<identifiant>/checkpoints/` : points de reprise validés.

Relancer la même commande reprend le travail. Utiliser un autre
`ODOO_MIGRATION_HOME` pour une autre source ou une nouvelle capture.
Les services Ollama restent démarrés après la fin de l'agent. `docker compose -f
docker-compose.ai.yml down` arrête la stack; ne pas ajouter `-v` si vous voulez
conserver les modèles. Les volumes d'essais créés par le moteur sont conservés.

## Variables facultatives

| Variable | Défaut | Usage |
|---|---|---|
| `SOURCE_CONTAINER` | obligatoire | Conteneur Odoo 12 source |
| `TARGET_VERSION` | `latest` | Dernière image stable officielle, ou cible explicite 13–20 |
| `SOURCE_DB_CONTAINER` | auto | Lever une ambiguïté réseau |
| `SOURCE_DATABASE` | auto | Limiter à une base servie, ou liste séparée par virgules |
| `ODOO_MIGRATION_HOME` | `/opt/odoo-ai-migration` | Dossier privé de travail sur l'hôte |
| `AI_MODEL` | `qwen3:8b` | Modèle Ollama à télécharger et charger |
| `AI_MAX_ACTIONS` | `16` | Budget maximal de décisions IA par base |
| `AI_TIMEOUT_SECONDS` | `900` | Délai d'une réponse du modèle |

## Limites et autorisations effectives

Ce moteur prend en charge une **source Odoo 12 CE** en architecture Docker standard.
Une configuration non standard, un filtre de bases dépendant du nom de domaine,
un PostgreSQL externe ou un réseau ambigu peuvent bloquer la découverte.
La cible est détectée automatiquement, mais une cible supérieure à 20 est refusée
jusqu'à adaptation du moteur. Aucune mise à jour de code non vérifiée ne s'installe seule.

Une version Odoo publiée n'implique pas que les migrations OpenUpgrade sont prêtes.
L'IA ne peut ni inventer une couverture, ni écrire dans les tables de couverture,
ni remplacer les contrôles. Une migration manquante, un écart comptable, du code de
module indisponible ou une dépendance système non prise en charge provoquent un
**arrêt documenté, sans question interactive**. Ce système n'offre donc pas la
garantie d'atteindre toute cible sans intervention humaine; il automatise les cas
pris en charge et certaines corrections de scripts.

Le résultat est une **copie migrée et sa sauvegarde complète**, pas un remplacement
automatique de la production. Traefik, DNS, intégrations et source restent inchangés
après la sauvegarde. Les fonctionnalités et données propres aux modules tiers
peuvent être supprimées de la copie par leur désinstallation ORM.

L'orchestrateur possède le socket Docker, donc des droits équivalents à root sur
l'hôte. Le modèle n'a que les actions codées (relancer, lire une source OpenUpgrade,
corriger un script existant, arrêter). Les scripts s'exécutent dans les conteneurs
de test, sans socket Docker ni montage hôte, sur réseau interne. Les données et
journaux restent locaux à cette stack. Aucun port Ollama n'est publié.

## Vérifications réalisées

Tests unitaires du moteur et de l'agent, simulation des réponses du modèle,
protection des chemins, traitement multi-bases, limite de boucle, refus des actions
inconnues, lecture des compétences et analyse du Compose. Les appels Docker et IA
sont simulés dans ces tests. **Aucun essai complet avec Docker, Ollama et la base
utilisateur n'a été exécuté dans l'environnement de préparation.**


## Compétence tierce Odoo Integration

La compétence de [txampa/claude-skill-odoo-integration](https://github.com/txampa/claude-skill-odoo-integration) est embarquée intégralement au commit `9c1def4043bd1ede1bea94fc1a54a72138e68920`, avec sa licence MIT et l'attribution à Txampa et JeanOnCode.

Le chargeur inclut réellement la référence dans le contexte du modèle, vérifie son SHA-256 et enregistre son empreinte avec les compétences locales. `50-odoo-integration.md` adapte son usage à cet agent. L'image Docker la copie avec tout le dossier `skills/`.

Elle couvre l'intégration XML-RPC et annonce Odoo 8–17. Elle ne fournit pas de scripts OpenUpgrade pour Odoo 20 et ne garantit pas la compatibilité des champs pour toutes les versions. Les exemples Node.js/Sheets/Railway restent des références; aucune synchronisation externe ni nouvelle écriture en production n'est activée. Le moteur garde ses actions et ses validations.

Pour une migration depuis un dump SQL et son filestore, voir [README-SQL.md](README-SQL.md).
