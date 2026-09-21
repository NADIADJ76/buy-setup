// En dev local, Vite proxifie /api vers http://localhost:8000 (voir vite.config.js).
// En production (build deploye sur Netlify), VITE_API_BASE_URL doit pointer vers
// l'URL publique du backend Render, ex: https://buy-setup-backend.onrender.com
const BASE = import.meta.env.VITE_API_BASE_URL || '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText} - ${text}`)
  }
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return res.json()
  return res
}

export const api = {
  // L'import Buyee reel peut prendre jusqu'a 1-2 minutes (navigateur reel +
  // connexion + eventuelle page de code de verification), et un plan Render
  // gratuit est lent. Garder une seule requete HTTP ouverte aussi longtemps
  // causait un "Failed to fetch" des que le telephone/le reseau coupait la
  // connexion, meme quand le serveur finissait par reussir un peu plus tard.
  // Le backend demarre donc l'import en arriere-plan et renvoie tout de
  // suite un job_id ; on interroge ensuite son statut par petites requetes
  // rapides (voir getImportStatus / ImportPage.jsx), ce qui evite d'avoir
  // une requete longue susceptible d'etre coupee.
  //
  // CONFIRMED 2026-09-21 : Buyee emet un code de verification DIFFERENT a
  // chaque tentative de connexion -- l'ancienne version renvoyait le code
  // avec identifiant+mot de passe en un seul appel, ce qui relancait a
  // chaque fois une connexion et invalidait donc le code avant meme de
  // l'utiliser. importInvoicesStart ne fait plus que la phase 1
  // (identifiant+mot de passe) ; si le job repond status:"code_required",
  // le code recu par email est soumis a part via verifyImportCode, qui
  // reprend EXACTEMENT la meme session en attente cote serveur.
  importInvoicesStart: (username, password) =>
    request('/invoices/import', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  verifyImportCode: (jobId, verificationCode) =>
    request(`/invoices/import/${jobId}/verify`, {
      method: 'POST',
      body: JSON.stringify({ verification_code: verificationCode }),
    }),
  getImportStatus: (jobId) => request(`/invoices/import/${jobId}`),
  importDemo: () => request('/invoices/demo', { method: 'POST' }),
  listArticles: () => request('/invoices'),
  getArticle: (id) => request(`/invoices/${id}`),
  updateArticle: (id, article) => request(`/invoices/${id}`, { method: 'PUT', body: JSON.stringify(article) }),
  deleteArticle: (id) => request(`/invoices/${id}`, { method: 'DELETE' }),

  costBreakdown: (inputs) => request('/pricing/breakdown', { method: 'POST', body: JSON.stringify(inputs) }),
  whatnotStrategy: (articleId, totalLandedCostEur, safetyMarginRate = 0.15) =>
    request(
      `/pricing/whatnot-strategy?article_id=${encodeURIComponent(articleId)}&total_landed_cost_eur=${totalLandedCostEur}&safety_margin_rate=${safetyMarginRate}`,
      { method: 'POST' },
    ),
  getCustomsRates: () => request('/pricing/customs-rates'),
  updateCustomsRates: (rates) => request('/pricing/customs-rates', { method: 'PUT', body: JSON.stringify(rates) }),

  listSales: () => request('/sales'),
  upsertSale: (sale) => request('/sales', { method: 'POST', body: JSON.stringify(sale) }),
  deleteSale: (id) => request(`/sales/${id}`, { method: 'DELETE' }),

  generateSheet: (articleId, inputs) =>
    request(`/sheet/${articleId}/generate`, { method: 'POST', body: JSON.stringify(inputs) }),
  sheetDownloadUrl: (articleId) => `${BASE}/sheet/${articleId}/download`,
}
