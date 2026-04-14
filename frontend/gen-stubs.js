const fs = require('fs');
const path = require('path');

const pages = {
  supervision: 'Supervision',
  equipements: 'Equipements', 
  predictions: 'Predictions',
  knowledge: 'Knowledge',
  sav: 'Sav',
  demandes: 'Demandes',
  planning: 'Planning',
  pieces: 'Pieces',
  reports: 'Reports',
  contrats: 'Contrats',
  conformite: 'Conformite',
  admin: 'Admin',
  clients: 'Clients',
  settings: 'Settings',
};

const labels = {
  supervision: 'Supervision',
  equipements: 'Equipements',
  predictions: 'Predictions',
  knowledge: 'Base de Connaissances',
  sav: 'SAV et Interventions',
  demandes: 'Demandes',
  planning: 'Planning',
  pieces: 'Pieces de Rechange',
  reports: 'Rapports',
  contrats: 'Contrats et SLA',
  conformite: 'QHSE Conformite',
  admin: 'Administration',
  clients: 'Clients SAVIA',
  settings: 'Parametres',
};

for (const [slug, name] of Object.entries(pages)) {
  const dir = path.join('src', 'app', '(authenticated)', slug);
  fs.mkdirSync(dir, { recursive: true });
  const content = `export default function ${name}Page() {
  return (
    <div className="animate-fade-in">
      <h1 className="text-2xl font-black gradient-text">${labels[slug]}</h1>
      <div className="glass rounded-xl p-8 mt-6 text-center">
        <div className="text-4xl mb-4">&#x1F6A7;</div>
        <p className="text-savia-text-muted">Page en cours de migration vers Next.js...</p>
        <p className="text-savia-text-dim text-sm mt-2">Cette section sera disponible prochainement.</p>
      </div>
    </div>
  );
}
`;
  fs.writeFileSync(path.join(dir, 'page.tsx'), content);
}

console.log('Created', Object.keys(pages).length, 'stub pages');
