import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'

export default function ImportPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [warnings, setWarnings] = useState([])
  const [importedCount, setImportedCount] = useState(null)
  const navigate = useNavigate()

  async function handleImport(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await api.importInvoices(username, password)
      setWarnings(res.warnings || [])
      setImportedCount(res.articles?.length ?? 0)
      setPassword('')
      if (res.articles?.length) navigate('/articles')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDemo() {
    setLoading(true)
    setError(null)
    try {
      const res = await api.importDemo()
      setWarnings(res.warnings || [])
      setImportedCount(res.articles?.length ?? 0)
      navigate('/articles')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="warning-box">
        Tes identifiants Buyee ne sont jamais enregistres : ils servent une seule fois
        pour cette connexion puis sont jetes (voir README du backend). Si le scraping
        ne trouve rien du premier coup, c'est probablement un selecteur a ajuster dans
        <code> buyee_scraper.py</code> contre ton vrai compte.
      </div>

      <div className="card">
        <h2>Importer mes factures Buyee</h2>
        <form onSubmit={handleImport}>
          <label>Identifiant Buyee</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          <label>Mot de passe Buyee</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <button type="submit" disabled={loading}>{loading ? 'Connexion...' : 'Importer mes factures'}</button>
          <button type="button" className="secondary" onClick={handleDemo} disabled={loading}>
            Charger des donnees de demo
          </button>
        </form>
        {error && <p style={{ color: 'var(--bad)' }}>{error}</p>}
        {importedCount !== null && <p>{importedCount} article(s) importe(s).</p>}
        {warnings.map((w, i) => (
          <div key={i} className="warning-box">{w}</div>
        ))}
      </div>
    </div>
  )
}
