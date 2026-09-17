import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

const PLATFORMS = ['whatnot', 'vinted', 'ebay', 'leboncoin', 'autre']
const STATUSES = ['a_lister', 'en_vente', 'vendu', 'invendu']

export default function SalesPage() {
  const [sales, setSales] = useState([])
  const [articles, setArticles] = useState({})
  const [form, setForm] = useState({ article_id: '', platform: 'whatnot', status: 'a_lister', listed_price_eur: '', sold_price_eur: '' })

  useEffect(() => {
    refresh()
    api.listArticles().then((list) => {
      const byId = {}
      list.forEach((a) => (byId[a.id] = a))
      setArticles(byId)
    })
  }, [])

  function refresh() {
    api.listSales().then(setSales)
  }

  async function handleAdd(e) {
    e.preventDefault()
    if (!form.article_id) return
    await api.upsertSale({
      id: '',
      article_id: form.article_id,
      platform: form.platform,
      status: form.status,
      listed_price_eur: form.listed_price_eur ? parseFloat(form.listed_price_eur) : null,
      sold_price_eur: form.sold_price_eur ? parseFloat(form.sold_price_eur) : null,
    })
    setForm({ article_id: '', platform: 'whatnot', status: 'a_lister', listed_price_eur: '', sold_price_eur: '' })
    refresh()
  }

  async function handleDelete(saleId) {
    await api.deleteSale(saleId)
    refresh()
  }

  function statusPill(status) {
    if (status === 'vendu') return <span className="pill good">Vendu</span>
    if (status === 'en_vente') return <span className="pill warn">En vente</span>
    if (status === 'invendu') return <span className="pill bad">Invendu</span>
    return <span className="pill">A lister</span>
  }

  return (
    <div>
      <div className="card">
        <h2>Suivi des ventes multi-plateformes</h2>
        <form onSubmit={handleAdd} className="two-col">
          <div>
            <label>Article</label>
            <select value={form.article_id} onChange={(e) => setForm({ ...form, article_id: e.target.value })} required>
              <option value="">-- choisir --</option>
              {Object.values(articles).map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
            <label>Plateforme</label>
            <select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>
              {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label>Statut</label>
            <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <label>Prix affiche (EUR)</label>
            <input type="number" step="0.01" value={form.listed_price_eur} onChange={(e) => setForm({ ...form, listed_price_eur: e.target.value })} />
            <label>Prix vendu (EUR)</label>
            <input type="number" step="0.01" value={form.sold_price_eur} onChange={(e) => setForm({ ...form, sold_price_eur: e.target.value })} />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <button type="submit">Ajouter / mettre a jour</button>
          </div>
        </form>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Article</th><th>Plateforme</th><th>Statut</th><th>Prix affiche</th><th>Prix vendu</th><th></th>
            </tr>
          </thead>
          <tbody>
            {sales.map((s) => (
              <tr key={s.id}>
                <td>{articles[s.article_id]?.name || s.article_id}</td>
                <td>{s.platform}</td>
                <td>{statusPill(s.status)}</td>
                <td>{s.listed_price_eur ?? '-'}</td>
                <td>{s.sold_price_eur ?? '-'}</td>
                <td><button className="danger" onClick={() => handleDelete(s.id)}>Suppr.</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
