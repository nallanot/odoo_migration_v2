# Migration Odoo 12 CE → 20 CE — stack Docker, un lancement

Déposer **dump.sql + le filestore complet**, puis déployer la stack. Elle importe
la copie, retire les modules tiers avec Odoo 12, enchaîne OpenUpgrade version par
version et exporte un ZIP Odoo complet après validation. Aucun jeton ChatGPT,
aucun compte cloud, aucun port Web ne sont nécessaires pour ce parcours.

**Limite actuelle : cette stack ne garantit pas que les scripts OCA disponibles
couvrent vos modules jusqu'à Odoo 20.** La couverture officielle est vérifiée
automatiquement pour chaque palier. Un module non couvert bloque la progression,
avec rapport et checkpoint; le programme ne fabrique pas un succès. Au 9 octobre
2026, le fichier de couverture 19→20 n'a pas été trouvé au chemin OCA vérifié.
La stack est préparée pour cette cible, pas certifiée sur une migration réelle 12→20.

## 1. Préparer les fichiers sur le serveur Docker

Créer `/opt/odoo-migration-input`, y placer :

- `/opt/odoo-migration-input/dump.sql`
- `/opt/odoo-migration-input/filestore/ab/abcdef…` et tous les autres sous-dossiers.

`filestore/` doit contenir directement les dossiers de fichiers; ne pas intercaler
le nom de la base. La copie doit être complète et figée. Le dossier est monté en
lecture seule. Limite d'entrée : 10 Gio SQL + filestore décompressés.

**Si des modules tiers sont installés**, déposer aussi leur code d'origine Odoo 12
dans `/opt/odoo-migration-input/addons-12/nom_du_module/`. Leur désinstallation ORM
peut nécessiter leurs dépendances Python d'origine. Un SQL et un filestore ne
contiennent pas ce code. Sans lui, la stack bloque proprement; elle ne supprime
pas des tables à l'aveugle. Les données propres aux modules désinstallés peuvent
être retirées de la copie. L'entrée et les sauvegardes initiales restent intactes.

## 2. Déployer depuis GitHub

Dans **Dockhand** :

- Dépôt : `https://github.com/nallanot/migration_odoo_community`
- Branche : `main`
- Fichier Compose : `docker-compose.migration.yml`
- Variables facultatives : `INPUT_DIR`, `ODOO_MIGRATION_HOME`, `TARGET_VERSION`.
- Déployer avec construction des images activée.

La migration démarre immédiatement. L'entrée doit donc être prête avant déploiement.
Les chemins sont ceux du serveur Docker, pas du poste client ni du conteneur Dockhand.
Les binds nécessitent un Docker local Linux et Compose v2, avec sortie Internet
pour télécharger les images, les sources et les dépendances. Le répertoire de
travail doit disposer d'assez de place pour les images et toutes les copies
intermédiaires; prévoir plusieurs fois le volume SQL + filestore, plus les images.

Ou, après clonage du dépôt sur le serveur :

```sh
docker compose -f docker-compose.migration.yml up -d --build
```

Suivi :

```sh
docker compose -f docker-compose.migration.yml logs -f migrator
```

Les valeurs par défaut sont dans `.env.migration.example`. Pour les modifier en
ligne de commande, copier ce fichier vers `.env` avant le lancement. `TARGET_VERSION`
reste **20** par défaut; une cible inférieure (13–19) doit être choisie explicitement.

## Résultat et reprise

- Succès : `/opt/odoo-migration-once/output/odoo-20-native.zip`.
- Rapport : `/opt/odoo-migration-once/output/result.json` (succès ou blocage).
- Journal : `/opt/odoo-migration-once/job/assistant.log`.
- Points validés : `/opt/odoo-migration-once/job/checkpoints/`.

Le ZIP contient `dump.sql`, `filestore/` et `manifest.json`, pour restauration dans
un Odoo CE de la **version effectivement validée**. Il n'est publié qu'après une
nouvelle restauration de contrôle. Le rapport contient sa somme SHA-256.
Le service sort avec le code **0** si terminé, **2** si bloqué. Aucun redémarrage
infini : corriger le blocage avant de relancer avec la même commande. Le moteur
reprend le dernier checkpoint et refuse un dump différent dans le même dossier.
Pour une autre sauvegarde, choisir un nouveau `ODOO_MIGRATION_HOME`.

Si une nouvelle couverture OCA est publiée, le clone local du palier est conservé
pour la reproductibilité. Un changement de sources doit être examiné et accompagné
d'une nouvelle couverture liée au commit; une relance seule ne met pas à jour Git.

## Contrôles intégrés

- SQL et filestore d'entrée inchangés, sauvegardes/checkpoints SHA-256.
- Restauration réelle et compteurs avant chaque migration, puis à l'export.
- Liste native officielle, désinstallation ORM, contrôle des dépendances.
- Couverture par module issue des tableaux officiels OCA et liée aux commits.
- Version réelle, états des modules, compteurs métier et totaux débit/crédit.
- Présence des fichiers référencés par les pièces jointes.
- Réseaux internes, absence de ports publics, montages hôte et privilèges dans
  les conteneurs d'essai; tâches planifiées et courriels neutralisés.

Les écarts légitimes dus à l'évolution du modèle comptable peuvent nécessiter une
analyse : ils ne sont pas ignorés. Ces contrôles ne remplacent pas une validation
métier finale. Aucun basculement de production n'est réalisé.

Le service orchestrateur utilise le socket Docker (droits équivalents à root sur
cet hôte). Les processus de migration n'ont pas ce socket. Utiliser un serveur
administré et garder le dossier de travail privé. Les volumes/essais restent
conservés pour diagnostic; aucun nettoyage global Docker n'est effectué.

## Vérification du code

```sh
python3 -m unittest discover -s odoo-migration-gui -p 'test_*.py'
```

Les tests locaux couvrent le moteur, l'authentification, les entrées, les reprises,
la couverture et l'export. Les appels Docker sont simulés dans les tests unitaires.
Une migration Docker réelle avec les données utilisateur n'a pas été exécutée dans
l'environnement de préparation; ne pas confondre ces tests avec une recette 12→20.

Le plugin ChatGPT optionnel reste dans `docker-compose.assistant.yml`. L'ancien
outil Web est conservé dans `docker-compose.legacy.yml` et n'est plus la stack par
défaut. Documentation du moteur natif : [README-agent-20.md](README-agent-20.md).
