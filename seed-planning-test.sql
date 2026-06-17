-- Script SQL pour ajouter une intervention de test dans le planning
-- Exécutez ceci dans la base de données PostgreSQL

INSERT INTO planning_maintenance (
  machine,
  client,
  date_prevue,
  technicien_assigne,
  type_maintenance,
  recurrence,
  statut,
  description,
  notes
) VALUES (
  'Radiologie CT-001',
  'Hôpital Test',
  CURRENT_DATE,  -- Date d'aujourd'hui
  'Jean Dupont, Marie Martin',
  'Préventive',
  'Aucune',
  'Planifiée',
  'Maintenance préventive de test',
  'Ceci est une intervention de test pour vérifier la fonctionnalité de reschedule'
);

-- Vérifiez que l'insertion a fonctionné:
SELECT id, machine, client, date_prevue, technicien_assigne, statut 
FROM planning_maintenance 
ORDER BY id DESC 
LIMIT 5;
