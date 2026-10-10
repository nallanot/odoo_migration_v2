# Intégration de la compétence txampa/claude-skill-odoo-integration

La référence originale et sa licence MIT sont embarquées dans references/txampa-odoo-integration/. Le commit et la somme SHA-256 sont fixés dans reference-index.json. Le moteur charge effectivement ce contenu dans le contexte IA; aucun téléchargement dynamique n'est effectué au démarrage.

## Usage dans cet agent
Utiliser les explications XML-RPC, modèles stock.picking, stock.move, sale.order, purchase.order, product.product, product.template et res.partner pour comprendre les diagnostics. Les conseils de pagination, déduplication et relations many2one sont des références de conception.
Cette compétence annonce Odoo 8–17. Ne pas extrapoler ses tableaux de champs à Odoo 18–20. Vérifier la version et le schéma réel dans les sources officielles avant de proposer une correction. Les exemples de champs et états ne sont pas une vérité universelle.

## Adaptation obligatoire au moteur de migration
Les compétences locales 00–40, le protocole JSON et les contrôles du moteur prévalent sur les prescriptions du document original. Les impératifs « Always use this class », les déploiements Railway, les exports Sheets, les tâches cron et les écritures create/write sont hors du mandat actuel.
Le runtime reste Python. La présence d'exemples Node.js n'installe ni Node.js, ni un client XML-RPC, ni de nouveaux outils dans l'agent. Ne jamais prétendre avoir testé un appel RPC avec les outils actuellement disponibles.
Ne pas créer d'utilisateur en production, ne pas réactiver les intégrations, ne pas exporter des données vers Google Sheets et ne pas lancer de synchronisation. Ne pas appliquer la consigne de continuer après une erreur à une migration : une erreur d'intégrité demeure bloquante.
Les affirmations générales de la référence sur la sécurité ou la compatibilité doivent être évaluées, pas reprises comme garanties. Cette compétence ne remplace ni OpenUpgrade ni ses scripts ni les validations indépendantes.
