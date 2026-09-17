import { NavLink, Route, Routes, Navigate } from 'react-router-dom'
import ImportPage from './pages/ImportPage.jsx'
import ArticlesPage from './pages/ArticlesPage.jsx'
import ArticleDetailPage from './pages/ArticleDetailPage.jsx'
import SalesPage from './pages/SalesPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <h1>Buy Setup</h1>
        <nav>
          <NavLink to="/" end>Import factures</NavLink>
          <NavLink to="/articles">Articles</NavLink>
          <NavLink to="/sales">Ventes</NavLink>
          <NavLink to="/settings">Reglages</NavLink>
        </nav>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<ImportPage />} />
          <Route path="/articles" element={<ArticlesPage />} />
          <Route path="/articles/:id" element={<ArticleDetailPage />} />
          <Route path="/sales" element={<SalesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
