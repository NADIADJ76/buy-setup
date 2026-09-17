import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

export default function SettingsPage() {
  const [rates, setRates] = useState({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.getCustomsRates().then(setRates)
  }, [])

  function updateRate(key, field, value) {
    setRates({ ...rates, [key]: { ...rates[key], [field]: parseFloat(value) } })
    setSaved(false)
  }

  async function handleSave() {
    await api.updateCustomsRates(rates)
    setSaved(true)
  }

  return (
    <div className="card">
      <h2>Reglages - Taux de douane France</h2>
      <p style={{ color: 'var(--muted)', fontSize: 13 }}>
        Valeurs indicatives par categorie. TVA appliquee depuis le premier euro,
        droits de douane appliques uniquement au-dela de 150 EUR de base taxable.
        Verifie toujours le taux exact sur le simulateur officiel des douanes avant
        une declaration reelle.
      </p>
      <table>
        <thead><tr><th>Categorie</th><th>Droits de douane (%)</th><th>TVA (%)</th></tr></thead>
        <tbody>
          {Object.entries(rates).map(([key, r]) => (
            <tr key={key}>
              <td>{r.label}</td>
              <td><input type="number" step="0.1" value={(r.duty_rate * 100).toFixed(1)} onChange={(e) => updateRate(key, 'duty_rate', e.target.value / 100)} /></td>
              <td><input type="number" step="0.1" value={(r.vat_rate * 100).toFixed(1)} onChange={(e) => updateRate(key, 'vat_rate', e.target.value / 100)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={handleSave}>Enregistrer</button>
      {saved && <span style={{ marginLeft: 10, color: 'var(--good)' }}>Enregistre.</span>}
    </div>
  )
}
