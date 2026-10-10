# Agent Odoo 12 → 20 CE — politique native v2

Le plugin privé existant crée désormais les nouveaux travaux avec une cible 20,
un nettoyage natif et le protocole moteur 2. Les travaux déjà créés conservent
leur cible 19; ne pas modifier un travail en cours. Créer un nouveau travail à
partir de la sauvegarde d'origine pour demander la politique native 20.

## Déploiement du moteur

Depuis le dépôt sur le serveur Docker, après mise à jour du code :

```sh
docker compose -f docker-compose.assistant.yml up -d --build assistant
```

Réutiliser les trois secrets MIGRATION_PLUGIN_* existants. Aucun nouveau jeton
n'est requis. Une reconstruction interrompt le moteur courant : attendre la fin
de son opération avant de le redéployer. Les checkpoints restent dans le volume.

Le moteur possède le socket Docker, donc des droits équivalents à root sur cet
hôte. Cette capacité doit rester privée. Les processus Odoo et PostgreSQL de
travail utilisent des volumes dédiés et un réseau interne. Aucune API shell
arbitraire n'est ajoutée au plugin. Le moteur ne peut pas s'octroyer de droits
supplémentaires dans ChatGPT, sur le serveur ou sur des services externes.

Pour SQL + filestore sans plugin, utiliser la stack par défaut décrite dans [README.md](README.md).

## Exécution

1. Import complet de la sauvegarde et du filestore sur une copie isolée.
2. Classification depuis les manifests du dépôt officiel `odoo/odoo`, branche 12.0.
3. Désinstallation ORM Odoo 12 des modules tiers, y compris OCA/Enterprise/personnalisés.
   Le code tiers initial doit être présent dans les addons sauvegardés ou `extra/12`.
   Un dump seul ne fournit généralement pas ce code. L'agent peut le déposer via
   `add_migration_file` version 12. Aucune suppression SQL forcée de métadonnées.
4. Contrôle des dépendants natifs, des compteurs protégés et des pièces jointes.
   Les données propres aux modules supprimés peuvent disparaître de la copie.
   Le rapport avant/après reste dans `native-cleanup/report.json`; l'original reste intact.
5. Migrations successives 12→13→14→15→16→17→18→19→20. Reprise au dernier checkpoint validé.
6. Couverture par module liée au commit OpenUpgrade, lue automatiquement dans
   les tableaux officiels OCA, ou renseignée via `set_migration_coverage` après examen des sources officielles. Une branche ou
   un fichier de migration existant n'est pas une preuve de couverture suffisante.
7. Contrôles de version réelle, états des modules, compteurs, totaux débit/crédit,
   présence des pièces jointes, restauration SHA-256 et des volumes associés.
8. Vérification du réseau interne, des ports non publiés, de l'absence de montages
   hôte et de conteneurs privilégiés dans les essais; tâches planifiées désactivées.

Les conteneurs d'essai restent disponibles pour diagnostic. La copie finale est
accessible uniquement via localhost/tunnel. Pas de basculement automatique de
production, de suppression de sauvegardes ou de réactivation d'intégrations.
Les addons OpenUpgrade servent au transport; ils ne sont pas admis comme modules
installés dans le résultat final natif.

## Limites vérifiables

Le moteur automatise les étapes connues et s'arrête sur les erreurs. ChatGPT,
lors d'une session active, peut examiner les diagnostics, documenter la couverture,
proposer des adaptations et relancer. Aucun appel LLM permanent en arrière-plan
n'est embarqué; il ne faut pas le présenter comme un réparateur illimité autonome.
L'examen métier, les changements comptables légitimes et les migrations OCA
incomplètes peuvent demander du travail supplémentaire. Aucun test ne garantit
l'absence de toute vulnérabilité. La version 20 ne remplace jamais silencieusement
la cible par 19.

Tests locaux : `python3 -m unittest discover -s odoo-migration-gui -p 'test_*.py'`.
Le passage réel sur Docker, avec la sauvegarde et les modules de l'utilisateur,
est indispensable avant de conclure que la migration est réussie.
