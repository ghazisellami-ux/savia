
// savia-pdf.js — Shared PDF utilities for SAVIA reports
// Requires: jsPDF + jspdf-autotable loaded in the same window

window.SAVIA_PDF = {

  /** Format number with space as thousand separator */
  fmt: function(n) {
    if (n === null || n === undefined || isNaN(n)) return '0';
    return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f');
  },

  /** Draw professional header on current page */
  drawHeader: async function(doc, pageW, opts) {
    const { companyName, companyLogo, saviaLogoB64, title, subtitle } = opts;
    let y = 12;
    let xNext = 10;

    // SAVIA logo (bigger, no text)
    if (saviaLogoB64) {
      try {
        doc.addImage(saviaLogoB64, 'PNG', 10, y, 52, 26);
        xNext = 68;
      } catch(e) { xNext = 10; }
    }

    // Vertical separator only if both logos exist
    if (companyLogo && saviaLogoB64) {
      doc.setDrawColor(190, 210, 205);
      doc.setLineWidth(0.4);
      doc.line(xNext, y + 2, xNext, y + 22);
      xNext += 5;
    }

    // Company logo
    if (companyLogo) {
      try {
        const ext = companyLogo.includes('data:image/png') ? 'PNG' : 'JPEG';
        doc.addImage(companyLogo, ext, xNext, y + 4, 32, 16);
        xNext += 38;
      } catch(e) { /* skip */ }
    }

    // Company name (bold, teal)
    if (companyName && companyName !== 'SAVIA') {
      doc.setFontSize(13);
      doc.setTextColor(15, 118, 110);
      doc.setFont(undefined, 'bold');
      const lines = doc.splitTextToSize(companyName, pageW - xNext - 15);
      doc.text(lines, xNext, y + 12);
      doc.setFont(undefined, 'normal');
    }

    // Separator line
    const sepY = y + 30;
    doc.setDrawColor(15, 118, 110);
    doc.setLineWidth(1.0);
    doc.line(10, sepY, pageW - 10, sepY);

    // Document title
    let ty = sepY + 9;
    doc.setFontSize(15);
    doc.setTextColor(15, 30, 50);
    doc.setFont(undefined, 'bold');
    doc.text(title || 'Rapport', 10, ty);
    doc.setFont(undefined, 'normal');

    if (subtitle) {
      ty += 7;
      doc.setFontSize(9);
      doc.setTextColor(100, 120, 140);
      doc.text(subtitle, 10, ty);
    }

    return ty + 10; // return Y after header
  },

  /** Draw KPI boxes */
  drawKpis: function(doc, kpis, startY) {
    const boxW = 64;
    const boxH = 16;
    const margin = 5;
    kpis.forEach((k, i) => {
      const kx = 10 + i * (boxW + margin);
      doc.setFillColor(242, 252, 250);
      doc.roundedRect(kx, startY, boxW, boxH, 3, 3, 'F');
      doc.setDrawColor(180, 220, 215);
      doc.setLineWidth(0.3);
      doc.roundedRect(kx, startY, boxW, boxH, 3, 3, 'S');
      doc.setFontSize(13);
      const rgb = k.color || [15, 118, 110];
      doc.setTextColor(...rgb);
      doc.setFont(undefined, 'bold');
      doc.text(String(k.val), kx + boxW / 2, startY + 9, { align: 'center' });
      doc.setFont(undefined, 'normal');
      doc.setFontSize(7);
      doc.setTextColor(100, 120, 130);
      doc.text(k.label, kx + boxW / 2, startY + 14, { align: 'center' });
    });
    return startY + boxH + 8;
  },

  /** Add paginated footer */
  addFooters: function(doc, companyName) {
    const pageCount = doc.internal.getNumberOfPages();
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();
    for (let p = 1; p <= pageCount; p++) {
      doc.setPage(p);
      doc.setFontSize(7);
      doc.setTextColor(170, 175, 195);
      doc.line(10, pageH - 11, pageW - 10, pageH - 11);
      doc.text(
        'G\u00e9n\u00e9r\u00e9 par ' + companyName + ' \u2014 ' + new Date().toLocaleString('fr-FR'),
        10, pageH - 6
      );
      doc.text('Page ' + p + ' / ' + pageCount, pageW - 20, pageH - 6, { align: 'right' });
    }
  },

  /** Load SAVIA logo from /logo-savia.png */
  loadSaviaLogo: async function() {
    try {
      const res = await fetch('/logo-savia.png');
      const blob = await res.blob();
      return await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
    } catch(e) { return null; }
  },

  /** Wait for jsPDF to be available */
  waitForJsPDF: async function(maxMs = 6000) {
    const start = Date.now();
    while (!window.jspdf && Date.now() - start < maxMs) {
      await new Promise(r => setTimeout(r, 150));
    }
    if (!window.jspdf) throw new Error('jsPDF non disponible');
    return window.jspdf;
  },

  /** Open PDF generation window and run the provided generator function */
  openPdfWindow: function(title, generatorFn) {
    const w = window.open('', '_blank', 'width=480,height=280');
    if (!w) { alert("Popup bloqué \u2014 autorisez les popups pour ce site."); return null; }
    w.document.write(`<!DOCTYPE html><html lang="fr"><head>
<meta charset="utf-8"><title>${title}</title>
<style>
body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',Arial,sans-serif;
     display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{text-align:center;padding:36px 56px;background:#1e293b;border-radius:14px;
      border:1px solid #334155;min-width:320px}
.spinner{width:44px;height:44px;border:4px solid #1e3a5f;border-top:4px solid #0d9488;
         border-radius:50%;animation:spin .9s linear infinite;margin:0 auto 18px}
@keyframes spin{to{transform:rotate(360deg)}}
#status{color:#64748b;font-size:13px;margin:6px 0 0}
#err{color:#f87171;font-size:12px;margin-top:10px;display:none}
</style>
</head><body>
<div class="card">
  <div class="spinner"></div>
  <p style="font-size:15px;font-weight:600;margin:0">${title}</p>
  <p id="status">Chargement...</p>
  <div id="err"></div>
</div>
<script src="/jspdf.umd.min.js"><\/script>
<script src="/jspdf.plugin.autotable.min.js"><\/script>
<script src="/savia-pdf.js"><\/script>
<script>
(async function() {
  const setStatus = m => { const el=document.getElementById('status'); if(el) el.textContent=m; };
  const showErr = m => { const el=document.getElementById('err'); if(el){el.textContent=m;el.style.display='block';} };
  try {
    setStatus('Chargement de jsPDF...');
    await SAVIA_PDF.waitForJsPDF();
    setStatus('Chargement du logo...');
    await (${generatorFn.toString()})(setStatus);
    setStatus('PDF t\u00e9l\u00e9charg\u00e9 !');
    setTimeout(() => window.close(), 1500);
  } catch(e) {
    showErr('Erreur: ' + e.message);
    console.error(e);
  }
})();
<\/script>
</body></html>`);
    w.document.close();
    return w;
  }
};
