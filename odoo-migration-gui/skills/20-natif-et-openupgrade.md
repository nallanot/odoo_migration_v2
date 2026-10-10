# Modules natifs et migrations
Référence principale : https://oca.github.io/OpenUpgrade/ (documentation officielle OCA, consultée le 2026-10-10). Elle prévaut sur la référence d'intégration txampa pour les migrations. Les liens sont documentaires : les actions actuelles de l'agent ne fournissent pas de navigateur Web.

Comparer les modules aux manifests officiels odoo/odoo de chaque version. Désinstaller les tiers avec l'ORM Odoo 12 uniquement sur une copie. Un module natif dépendant d'un module supprimé bloque le nettoyage.
Enchaîner les paliers sans en sauter. Une image Docker et une branche Git existantes ne prouvent pas la disponibilité de la migration. Le tableau officiel OCA doit indiquer Done ou Nothing to do pour chaque module.
Ne jamais inventer de preuve de couverture ni écrire Done dans un tableau pour débloquer un palier. Une absence de couverture ou une nouvelle version hors du support du moteur exige stop avec le palier et les modules concernés.
Les renommages et fusions officiels sont appliqués à partir d'apriori.py. Ne pas supprimer un module simplement pour faire disparaître une erreur.

Procédure : https://oca.github.io/OpenUpgrade/040_run_migration.html
La branche cible N migre depuis N-1. Jusqu'à 13, utiliser le fork OpenUpgrade; à partir de 14, utiliser Odoo avec openupgrade_framework et openupgrade_scripts. Le moteur orchestre --update all et --stop-after-init, ainsi que --load=base,web,openupgrade_framework à partir de 14. Vérifier openupgradelib et les commits enregistrés lors de la préparation. Ne pas modifier les options d'exécution avec patch_script.

Couverture : https://oca.github.io/OpenUpgrade/030_coverage_analysis.html
Lors de cette consultation, le dernier palier lié était 18→19. Cela ne prouve pas la disponibilité de 19→20. Pour chaque travail, la décision repose sur la couverture des modules de la branche effectivement préparée, conservée avec son commit; cette observation datée ne fixe pas une limite permanente à 19.
