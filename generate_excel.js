const fs = require('fs');
const path = require('path');

// Sample data
const headers = ['nom', 'code_client', 'matricule_fiscale', 'ville', 'region', 'contact', 'telephone', 'adresse', 'type_client'];
const data = [
  ['Hôpital Central Tunis', 'HC-001', '1234567890', 'Tunis', 'Nord', 'Dr. Ahmed Ben Ali', '+216 71 123 456', '123 Avenue de la Liberté - Tunis', 'Privé'],
  ['Clinique Sousse', 'CS-002', '0987654321', 'Sousse', 'Centre', 'Dr. Fatima Karray', '+216 73 234 567', '456 Rue de la Paix - Sousse', 'Privé'],
  ['Laboratoire Sfax', 'LS-003', '1122334455', 'Sfax', 'Centre', 'Mr. Mohamed Jebali', '+216 74 345 678', '789 Boulevard Habib Bourguiba - Sfax', 'Privé'],
  ['Polyclinique Bizerte', 'PB-004', '5566778899', 'Bizerte', 'Nord', 'Dr. Leila Mansouri', '+216 72 456 789', '321 Rue de l\'Indépendance - Bizerte', 'Public'],
  ['Centre Médical Ariana', 'CMA-005', '9988776655', 'Ariana', 'Nord', 'Mr. Karim Belhadj', '+216 71 567 890', '654 Avenue Mohamed V - Ariana', 'Privé'],
  ['Hôpital Régional Kairouan', 'HRK-006', '4433221100', 'Kairouan', 'Centre', 'Dr. Nadia Trabelsi', '+216 77 678 901', '987 Rue de la Révolution - Kairouan', 'Public'],
  ['Clinique Privée Ben Arous', 'CPBA-007', '7788990011', 'Ben Arous', 'Nord', 'Dr. Sami Gharbi', '+216 71 789 012', '147 Avenue de la République - Ben Arous', 'Privé'],
  ['Centre de Diagnostic Monastir', 'CDM-008', '2211334455', 'Monastir', 'Centre', 'Mr. Youssef Mami', '+216 73 890 123', '258 Rue Habib Thameur - Monastir', 'Privé'],
  ['Hôpital Universitaire Mahdia', 'HUM-009', '6655443322', 'Mahdia', 'Centre', 'Dr. Amira Bouaziz', '+216 73 901 234', '369 Boulevard de la Corniche - Mahdia', 'Public'],
  ['Clinique Internationale Tunis', 'CIT-010', '3344556677', 'Tunis', 'Nord', 'Dr. Riadh Zahra', '+216 71 012 345', '741 Avenue Habib Bourguiba - Tunis', 'Privé'],
];

// Create CSV content
let csv = headers.join(',') + '\n';
data.forEach(row => {
  csv += row.map(cell => {
    // Escape quotes and wrap in quotes if contains comma or special chars
    if (typeof cell === 'string' && (cell.includes(',') || cell.includes('"') || cell.includes('\n'))) {
      return '"' + cell.replace(/"/g, '""') + '"';
    }
    return cell;
  }).join(',') + '\n';
});

// Write CSV file
fs.writeFileSync(path.join(__dirname, 'clients_import_sample_clean.csv'), csv, 'utf8');
console.log('CSV file created: clients_import_sample_clean.csv');

// Try to create Excel file if xlsx is available
try {
  const XLSX = require('xlsx');
  
  // Create workbook
  const ws = XLSX.utils.aoa_to_sheet([headers, ...data]);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Clients');
  
  // Set column widths
  ws['!cols'] = [
    { wch: 25 },  // nom
    { wch: 12 },  // code_client
    { wch: 15 },  // matricule_fiscale
    { wch: 15 },  // ville
    { wch: 12 },  // region
    { wch: 20 },  // contact
    { wch: 15 },  // telephone
    { wch: 35 },  // adresse
    { wch: 12 },  // type_client
  ];
  
  XLSX.writeFile(wb, path.join(__dirname, 'clients_import_sample_clean.xlsx'));
  console.log('Excel file created: clients_import_sample_clean.xlsx');
} catch (err) {
  console.log('XLSX not available, only CSV created');
}
