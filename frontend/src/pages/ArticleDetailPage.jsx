import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api.js'

const DEFAULT_JPY_EUR_RATE = 0.0062 // ~1 EUR = 161 JPY, ajuste selon le taux du jour

export default function ArticleDetailPage() {
  const { id } = useParams()
  const [article, setArticle] = useState(null)
  const [rates, setRates] = useState({})
  const [form, setForm] = useState({
    international_shipping_eur: 9,
    jpy_to_eur_rate: DEFAULT_JPY_EUR_RATE,
    category: 'default',
  })
  const [cost, setCost] = useState(null)
  const [strategy, setStrategy] = useState(null)
  const [error, setError] = useState(null)
  const [sheetUrl, setSheetUrl] = useState(null)

  useEffect(() => {
    api.getArticle(id).then((a) => {
      setArticle(a)
      setForm((f) => ({
        ...f,
        category: a.category || 'default',
        // Pre-remplit avec les vraies valeurs Buyee quand elles sont
        // disponibles (colis deja expedie) -- reste modifiable.
        international_shipping_eur:
          a.international_shipping_eur != null ? a.international_shipping_eur : f.international_shipping_eur,
        jpy_to_eur_rate:
          a.buyee_price_eur && a.item_price_jpy
            ? +(a.buyee_price_eur / a.item_price_jpy).toFixed(6)
            : f.jpy_to_eur_rate,
      }))
    })
    api.getCustomsRates().then(setRates)
  }, [id])

  async function handleCompute(e) {
    e.preventDefault()
    setError(null)
    try {
      const inputs = {
        article_id: id,
        item_price_jpy: article.item_price_jpy,
        japan_domestic_shipping_jpy: article.japan_domestic_shipping_jpy,
        international_shipping_eur: parseFloat(form.international_shipping_eur),
        jpy_to_eur_rate: parseFloat(form.jpy_to_eur_rate),
        category: form.category,
      }
      const c = await api.costBreakdown(inputs)
      setCost(c)
      const s = await api.whatnotStrategy(id, c.total_landed_cost_eur)
      setStrategy(s)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleGenerateSheet() {
    if (!cost) return
    const inputs = {
      article_id: id,
      item_price_jpy: article.item_price_jpy,
      japan_domestic_shipping_jpy: article.japan_domestic_shipping_jpy,
      international_shipping_eur: parseFloat(form.international_shipping_eur),
      jpy_to_eur_rate: parseFloat(form.jpy_to_eur_rate),
      category: form.category,
    }
    await api.generateSheet(id, inputs)
    setSheetUrl(api.sheetDownloadUrl(id))
  }

  if (!article) return <p>Chargement...</p>

  return (
    <div>
      <div className="card">
        <h2>{article.name}</h2>
        <div className="two-col">
          <div>
            {article.photo_url && <img src={article.photo_url} alt={article.name} style={{ width: '100%', borderRadius: 8 }} />}
          </div>
          <div>
            <p>Prix article : {article.item_price_jpy} JPY{article.buyee_price_eur ? ` (~${article.buyee_price_eur.toFixed(2)} EUR selon Buyee)` : ''}</p>
            <p>Livraison domestique Japon (Buyee) : {article.japan_domestic_shipping_jpy} JPY</p>
            {article.international_shipping_jpy > 0 && (
              <p>
                Livraison internationale Japon -&gt; France (Buyee) : {article.international_shipping_jpy.toFixed(0)} JPY
                {article.international_shipping_eur ? ` (~${article.international_shipping_eur.toFixed(2)} EUR)` : ''}
                <br />
                <small style={{ color: 'var(--muted)' }}>
                  Repartie a parts egales si ton colis contenait plusieurs articles -- champ pre-rempli ci-dessous, modifiable.
                </small>
              </p>
            )}

            <form onSubmit={handleCompute}>
              <label>Taux de change JPY -&gt; EUR (ex: 0.0062)</label>
              <input
                type="number" step="0.0001"
                value={form.jpy_to_eur_rate}
                onChange={(e) => setForm({ ...form, jpy_to_eur_rate: e.target.value })}
              />
              <label>Livraison internationale Japon -&gt; France (EUR)</label>
              <input
                type="number" step="0.01"
                value={form.international_shipping_eur}
                onChange={(e) => setForm({ ...form, international_shipping_eur: e.target.value })}
              />
              <label>Categorie douaniere</label>
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {Object.entries(rates).map(([key, r]) => (
                  <option key={key} value={key}>{r.label} (droits {(r.duty_rate * 100).toFixed(1)}%, TVA {(r.vat_rate * 100).toFixed(1)}%)</option>
                ))}
              </select>
              <button type="submit">Calculer le prix de revient</button>
            </form>
          </div>
        </div>
        {error && <p style={{ color: 'var(--bad)' }}>{error}</p>}
      </div>

      {cost && (
        <div className="card">
          <h2>Prix de revient</h2>
          <div className="cost-line"><span>Article</span><span>{cost.item_price_eur.toFixed(2)} EUR</span></div>
          <div className="cost-line"><span>Livraison Japon (domestique)</span><span>{cost.japan_domestic_shipping_eur.toFixed(2)} EUR</span></div>
          <div className="cost-line"><span>Livraison internationale</span><span>{cost.international_shipping_eur.toFixed(2)} EUR</span></div>
          <div className="cost-line"><span>Droits de douane ({(cost.customs_duty_rate * 100).toFixed(1)}%)</span><span>{cost.customs_duty_eur.toFixed(2)} EUR</span></div>
          <div className="cost-line"><span>TVA ({(cost.vat_rate * 100).toFixed(1)}%)</span><span>{cost.vat_eur.toFixed(2)} EUR</span></div>
          <div className="cost-line total"><span>Total</span><span>{cost.total_landed_cost_eur.toFixed(2)} EUR</span></div>
        </div>
      )}

      {strategy && (
        <div className="card">
          <h2>Strategie enchere WhatNot</h2>
          <p>
            {strategy.can_start_at_1_eur
              ? <span className="pill good">Depart a 1 EUR OK</span>
              : <span className="pill warn">Depart a 1 EUR risque</span>}
          </p>
          <div className="cost-line"><span>Prix minimum viable (marge {(strategy.safety_margin_rate * 100).toFixed(0)}% + frais WhatNot)</span><span>{strategy.min_viable_price_eur.toFixed(2)} EUR</span></div>
          <div className="cost-line"><span>Prix de depart conseille</span><span>{strategy.suggested_start_price_eur.toFixed(2)} EUR</span></div>
          <div className="cost-line"><span>Seuil x2</span><span>{strategy.x2_threshold_eur.toFixed(2)} EUR</span></div>
          <div className="cost-line"><span>Seuil x3</span><span>{strategy.x3_threshold_eur.toFixed(2)} EUR</span></div>
          <p style={{ fontSize: 13, color: 'var(--muted)' }}>{strategy.notes}</p>

          <button onClick={handleGenerateSheet}>Generer la fiche WhatNot (PDF)</button>
          {sheetUrl && <a href={sheetUrl} target="_blank" rel="noreferrer" style={{ marginLeft: 8 }}>Telecharger la fiche</a>}
        </div>
      )}
    </div>
  )
}
