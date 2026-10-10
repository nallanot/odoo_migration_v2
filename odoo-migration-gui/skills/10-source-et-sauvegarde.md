# Source et sauvegarde
L'agent identifie le PostgreSQL partageant le réseau du conteneur source et traite toutes les bases Odoo 12 servies lorsque db_name n'est pas fixé. Si une association est ambiguë, arrêter avec un diagnostic précis plutôt que choisir arbitrairement.
Une sauvegarde cohérente nécessite un arrêt temporaire du conteneur Odoo. Le moteur est autorisé à cet arrêt et doit le redémarrer dans un finally, même en cas d'échec. PostgreSQL source reste actif. Les systèmes externes qui écrivent directement dans la base doivent être figés séparément.
Les sauvegardes, le filestore, les modules initiaux, la configuration et les sommes de contrôle doivent être préservés. Ne jamais modifier la source pendant les corrections.
