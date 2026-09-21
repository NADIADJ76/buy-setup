import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'

export default function ArticlesPage() {
  const [articles, setArticles] = useState([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState(null)

  useEffect(() => {
    api.listArticles().then(setArticles).finally(() => setLoading(false))
  }, [])

  // Permet de supprimer un article -- utile en particulier pour retirer les
  // exemples charges par "Charger des donnees de demo" une fois que les
  // vrais imports Buyee fonctionnent, pour ne pas les confondre avec tes
  // vraies factures.
  async function handleDelete(e, id) {
    e.preventDefault()
    e.stopPropagation()
    if (!window.confirm('Supprimer cet article ?')) return
    setDeletingId(id)
    try {
      await api.deleteArticle(id)
      setArticles((prev) => prev.filter((a) => a.id !== id))
    } catch (err) {
      window.alert(`Impossible de supprimer : ${err.message}`)
    } finally {
      setDeletingId(null)
    }
  }

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
        <Link key={a.id} to={`/articles/${a.id}`} className="article-card" style={{ position: 'relative' }}>
          <button
            type="button"
            onClick={(e) => handleDelete(e, a.id)}
            disabled={deletingId === a.id}
            title="Supprimer cet article"
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              zIndex: 1,
              background: 'rgba(0,0,0,0.6)',
              color: '#fff',
              border: 'none',
              borderRadius: 4,
              padding: '2px 8px',
              cursor: 'pointer',
            }}
          >
            {deletingId === a.id ? '...' : '✕'}
          </button>
          {a.photo_url ? <img src={a.photo_url} alt={a.name} /> : <div style={{ height: 140, background: '#232735', borderRadius: 6 }} />}
          <div className="name">{a.name}</div>
          <div className="price">{a.item_price_jpy} JPY + {a.japan_domestic_shipping_jpy} JPY port JP</div>
        </Link>
      ))}
    </div>
  )
}
