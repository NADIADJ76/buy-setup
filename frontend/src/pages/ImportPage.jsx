import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'

export default function ImportPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [verificationCode, setVerificationCode] = useState('')
  const [needsVerificationCode, setNeedsVerificationCode] = useState(false)
  const [jobId, setJobId] = useState(null)
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

  // Interroge le statut d'un job par petites requetes rapides plutot que de
  // garder une seule requete ouverte plusieurs minutes (voir isNetworkBlip
  // ci-dessus pour la tolerance aux coupures reseau isolees). Partagee par
  // la phase 1 (identifiant+mot de passe) et la phase 2 (code recu par
  // email), qui utilisent toutes les deux le meme job_id.
  async function pollJob(id) {
    let res = null
    let consecutiveBlips = 0
    for (let i = 0; i < 120; i++) {
      await sleep(3000)
      try {
        res = await api.getImportStatus(id)
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
    return res
  }

  // CONFIRMED ROOT CAUSE on 2026-09-21 : Buyee envoie un nouveau code de
  // verification par email a CHAQUE tentative de connexion. L'ancienne
  // version renvoyait identifiant+mot de passe+code en un seul appel, ce
  // qui relancait une connexion et invalidait donc le code avant meme de
  // l'utiliser -- ce qui expliquait les echecs systematiques malgre
  // plusieurs corrections de la saisie du code. L'import se fait desormais
  // en deux etapes : handleImport ne fait QUE la connexion
  // identifiant+mot de passe ; si Buyee demande un code, le job reste en
  // attente (status "code_required") et c'est handleVerifyCode, plus bas,
  // qui soumet le code a part en reprenant EXACTEMENT cette meme session.
  async function handleImport(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setStatusMessage(
      'Connexion a Buyee en cours... ca peut prendre 1 a 2 minutes (navigateur reel, '
        + 'et le serveur gratuit peut avoir besoin de se reveiller). Reste sur cette page '
        + 'en attendant.'
    )
    try {
      // Le tout premier appel (demarrage du job) peut lui-meme tomber sur un
      // blip reseau pendant que le serveur gratuit se reveille -- quelques
      // tentatives silencieuses avant d'abandonner.
      let id = null
      for (let attempt = 1; ; attempt++) {
        try {
          const started = await api.importInvoicesStart(username, password)
          id = started.job_id
          break
        } catch (err) {
          if (!isNetworkBlip(err) || attempt >= 5) throw err
          await sleep(3000)
        }
      }
      setJobId(id)

      const res = await pollJob(id)
      if (res.status === 'code_required') {
        setWarnings(res.warnings || [])
        setNeedsVerificationCode(true)
        setStatusMessage(null)
        return
      }
      const w = res.warnings || []
      setWarnings(w)
      setImportedCount(res.articles?.length ?? 0)
      setNeedsVerificationCode(false)
      if (res.articles?.length) navigate('/articles')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
      setStatusMessage(null)
    }
  }

  async function handleVerifyCode(e) {
    e.preventDefault()
    if (!jobId) return
    setLoading(true)
    setError(null)
    setStatusMessage('Validation du code en cours... quelques dizaines de secondes.')
    try {
      for (let attempt = 1; ; attempt++) {
        try {
          await api.verifyImportCode(jobId, verificationCode)
          break
        } catch (err) {
          if (!isNetworkBlip(err) || attempt >= 5) throw err
          await sleep(3000)
        }
      }

      const res = await pollJob(jobId)
      if (res.status === 'code_required') {
        // Toujours en attente : soit le code etait incorrect/perime, soit
        // la page a change de forme -- le backend explique quoi dans
        // warnings (voir buyee_scraper.py). On reste sur cette etape pour
        // permettre de reessayer avec un nouveau code.
        setWarnings(res.warnings || [])
        setStatusMessage(null)
        return
      }
      const w = res.warnings || []
      setWarnings(w)
      setImportedCount(res.articles?.length ?? 0)
      setNeedsVerificationCode(false)
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

        {!needsVerificationCode && (
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
        )}

        {needsVerificationCode && (
          <form onSubmit={handleVerifyCode}>
            <p>
              Buyee a envoye un code de verification par email pour cette connexion.
              Verifie ta boite mail (y compris les spams), et saisis ici le code du
              DERNIER email recu -- un nouveau code est genere a chaque tentative, donc
              un ancien code ne fonctionnera pas.
            </p>
            <label>Code de verification Buyee (recu par email)</label>
            <input
              value={verificationCode}
              onChange={(e) => setVerificationCode(e.target.value)}
              placeholder="ex: 402010"
              required
            />
            <button type="submit" disabled={loading}>{loading ? 'Validation...' : 'Valider le code'}</button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setNeedsVerificationCode(false)
                setJobId(null)
                setVerificationCode('')
              }}
              disabled={loading}
            >
              Recommencer la connexion
            </button>
          </form>
        )}

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
