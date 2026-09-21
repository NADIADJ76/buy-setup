import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'

export default function ImportPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [verificationCode, setVerificationCode] = useState('')
  const [needsVerificationCode, setNeedsVerificationCode] = useState(false)
  const [loading, setLoading] = useState(false)
  const [statusMessage, setStatusMessage] = useState(null)
  const [error, setError] = useState(null)
  const [warnings, setWarnings] = useState([])
  const [importedCount, setImportedCount] = useState(null)
  const navigate = useNavigate()

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }

  // CONFIRMED BUG on 2026-09-21: le serveur gratuit s'endort apres un
  // moment d'inactivite et se reveille au vol sur la requete suivante --
  // les journaux du serveur montraient le tout premier import apres un
  // reveil reussir cote serveur (POST 200, plusieurs GET de suivi 200 OK,
  // le navigateur Buyee termine proprement), mais l'appli affichait quand
  // meme "Failed to fetch" : UNE seule requete de suivi avait du se perdre
  // en route juste apres le reveil du serveur, et comme la boucle
  // abandonnait au premier echec, tout le suivi s'arretait alors que le
  // serveur continuait de travailler tout seul derriere, pour rien.
  // isNetworkBlip distingue cet echec reseau ponctuel (fetch() lui-meme
  // rejete, err.name === 'TypeError') d'une vraie erreur renvoyee par le
  // serveur une fois la requete arrivee (ex: 502 parce que l'import a
  // vraiment echoue) -- seul le premier cas merite d'etre retente en
  // silence plutot que de faire abandonner tout l'import.
  function isNetworkBlip(err) {
    return err instanceof TypeError || /failed to fetch/i.test(err?.message || '')
  }

  async function handleImport(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setStatusMessage(
      'Connexion a Buyee en cours... ca peut prendre 1 a 2 minutes (navigateur reel + '
        + 'eventuelle page de code, et le serveur gratuit peut avoir besoin de se '
        + 'reveiller). Reste sur cette page en attendant.'
    )
    try {
      // Le tout premier appel (demarrage du job) peut lui-meme tomber sur un
      // blip reseau pendant que le serveur gratuit se reveille -- quelques
      // tentatives silencieuses avant d'abandonner.
      let jobId = null
      for (let attempt = 1; ; attempt++) {
        try {
          const started = await api.importInvoicesStart(username, password, verificationCode)
          jobId = started.job_id
          break
        } catch (err) {
          if (!isNetworkBlip(err) || attempt >= 5) throw err
          await sleep(3000)
        }
      }

      // On interroge le statut par petites requetes rapides plutot que de
      // garder une seule requete ouverte plusieurs minutes -- c'est cette
      // requete longue qui provoquait le "Failed to fetch" des que le
      // reseau du telephone la coupait, meme quand Buyee finissait par
      // repondre correctement un peu plus tard. Un blip reseau isole sur
      // UNE requete de suivi ne doit plus, non plus, faire abandonner tout
      // le suivi (voir isNetworkBlip ci-dessus) -- seulement plusieurs
      // echecs reseau D'AFFILEE.
      let res = null
      let consecutiveBlips = 0
      for (let i = 0; i < 120; i++) {
        await sleep(3000)
        try {
          res = await api.getImportStatus(jobId)
          consecutiveBlips = 0
        } catch (err) {
          if (!isNetworkBlip(err) || ++consecutiveBlips >= 5) throw err
          continue
        }
        if (res.status !== 'running') break
      }
      if (!res || res.status === 'running') {
        throw new Error("L'import prend anormalement longtemps (plus de 5-6 minutes), reessaie plus tard.")
      }
      const w = res.warnings || []
      setWarnings(w)
      setImportedCount(res.articles?.length ?? 0)
      // Le backend explique en clair qu'un code de verification Buyee est
      // necessaire -- on affiche alors le champ pour le saisir au prochain essai.
      setNeedsVerificationCode(w.some((msg) => msg.toLowerCase().includes('code de verification')))
      if (res.articles?.length) navigate('/articles')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
      setStatusMessage(null)
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
          {needsVerificationCode && (
            <>
              <label>Code de verification Buyee (recu par email)</label>
              <input
                value={verificationCode}
                onChange={(e) => setVerificationCode(e.target.value)}
                placeholder="ex: 402010"
              />
            </>
          )}
          <button type="submit" disabled={loading}>{loading ? 'Connexion...' : 'Importer mes factures'}</button>
          <button type="button" className="secondary" onClick={handleDemo} disabled={loading}>
            Charger des donnees de demo
          </button>
        </form>
        {statusMessage && <p>{statusMessage}</p>}
        {error && <p style={{ color: 'var(--bad)' }}>{error}</p>}
        {importedCount !== null && <p>{importedCount} article(s) importe(s).</p>}
        {warnings.map((w, i) => (
          <div key={i} className="warning-box">{w}</div>
        ))}
      </div>
    </div>
  )
}
