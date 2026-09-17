import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'

export default function ArticlesPage() {
  const [articles, setArticles] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.listArticles().then(setArticles).finally(() => setLoading(false))
  }, [])

  if (loading) return <p>Chargement...</p>
  if (!articles.length) {
    return (
      <div className="card">
        <p>Aucun article encore importe. Va dans "Import factures" pour recuperer tes commandes Buyee (ou charge les donnees de demo).</p>
      </div>
    )
  }

  return (
    <div className="grid">
      {articles.map((a) => (
        <Link key={a.id} to={`/articles/${a.id}`} className="article-card">
          {a.photo_url ? <img src={a.photo_url} alt={a.name} /> : <div style={{ height: 140, background: '#232735', borderRadius: 6 }} />}
          <div className="name">{a.name}</div>
          <div className="price">{a.item_price_jpy} JPY + {a.japan_domestic_shipping_jpy} JPY port JP</div>
        </Link>
      ))}
    </div>
  )
}
