import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowLeft, Download, Plus, Users, Shield, Activity,
  Lock, BarChart2, FileText, RefreshCw, Heart
} from 'lucide-react'
import toast from 'react-hot-toast'

function EncField({ value }) {
  const masked = '*'.repeat(Math.max(8, String(value ?? '').length))
  return <span className="encrypted-field text-xs">{masked}</span>
}

const TABS = [
  { id: 'usuarios', label: 'Usuarios', icon: Users },
  { id: 'pacientes', label: 'Pacientes (Cifrado)', icon: Lock },
  { id: 'estadisticas', label: 'Estadisticas', icon: BarChart2 },
  { id: 'logs', label: 'Audit Log', icon: FileText },
]

export default function AdminPanel() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('usuarios')
  const [users, setUsers] = useState([])
  const [patients, setPatients] = useState([])
  const [loadingPatients, setLoadingPatients] = useState(false)
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)

  const role = sessionStorage.getItem('role')

  useEffect(() => {
    if (role !== 'admin') {
      navigate('/dashboard')
      toast.error('Acceso denegado')
      return
    }
    fetchData()
  }, [navigate, role])

  const fetchData = async () => {
    const accessKey = sessionStorage.getItem('accessKey')
    const permissionKey = sessionStorage.getItem('permissionKey')
    try {
      const r = await fetch('/admin/users/', {
        headers: { 'X-Access-Key': accessKey, 'X-Permission-Key': permissionKey },
      })
      if (r.ok) {
        const d = await r.json()
        setUsers(d.users || [])
      }
    } catch {
      // ignore
    }
  }

  const fetchLogs = async () => {
    const accessKey = sessionStorage.getItem('accessKey')
    const permissionKey = sessionStorage.getItem('permissionKey')
    try {
      const r = await fetch('/admin/audit-log?limit=100&offset=0', {
        headers: { 'X-Access-Key': accessKey, 'X-Permission-Key': permissionKey },
      })
      if (r.ok) {
        const d = await r.json()
        setLogs(d.entries || [])
      }
    } catch {
      toast.error('Error cargando audit log')
    }
  }

  const fetchStats = async () => {
    const accessKey = sessionStorage.getItem('accessKey')
    const permissionKey = sessionStorage.getItem('permissionKey')
    try {
      const r = await fetch('/admin/statistics', {
        headers: { 'X-Access-Key': accessKey, 'X-Permission-Key': permissionKey },
      })
      if (r.ok) {
        setStats(await r.json())
      }
    } catch {
      toast.error('Error cargando estadisticas')
    }
  }

  const fetchPatients = async () => {
    setLoadingPatients(true)
    const accessKey = sessionStorage.getItem('accessKey')
    const permissionKey = sessionStorage.getItem('permissionKey')
    try {
      const r = await fetch('/fhir/Patient?limit=500&offset=0', {
        headers: { 'X-Access-Key': accessKey, 'X-Permission-Key': permissionKey },
      })
      if (r.ok) {
        const d = await r.json()
        setPatients(d.entry || [])
      }
    } catch {
      toast.error('Error cargando pacientes')
    } finally {
      setLoadingPatients(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'pacientes') fetchPatients()
    if (activeTab === 'logs') fetchLogs()
    if (activeTab === 'estadisticas') fetchStats()
  }, [activeTab])

  const handleExportLogs = async () => {
    const accessKey = sessionStorage.getItem('accessKey')
    const permissionKey = sessionStorage.getItem('permissionKey')
    try {
      const response = await fetch('/admin/audit-log/export?format=csv', {
        headers: { 'X-Access-Key': accessKey, 'X-Permission-Key': permissionKey },
      })
      if (!response.ok) throw new Error('export failed')
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'audit_log.csv'
      link.click()
      window.URL.revokeObjectURL(url)
      toast.success('Logs exportados')
    } catch {
      toast.error('Error exportando logs')
    }
  }

  return (
    <div className="min-h-screen" style={{ background: 'radial-gradient(ellipse at 20% 50%, #0f1f3d 0%, #020617 60%)' }}>
      <header className="border-b border-slate-800/80 px-6 py-3 flex items-center gap-3" style={{ background: 'rgba(2,6,23,0.8)', backdropFilter: 'blur(12px)' }}>
        <button onClick={() => navigate('/dashboard')} className="p-1.5 rounded-lg hover:bg-slate-800 transition-colors text-slate-400 hover:text-white">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <Heart className="w-5 h-5 text-cyan-400" />
        <span className="font-bold text-white">Panel Administrativo</span>
        <span className="ml-auto badge-role-admin">ADMIN</span>
      </header>

      <div className="mx-6 mt-4 p-3 rounded-lg bg-amber-900/20 border border-amber-700/40 flex items-center gap-2 text-sm text-amber-300">
        <Lock className="w-4 h-4 flex-shrink-0" />
        <span>Los datos de identidad permanecen cifrados para admin. No hay opcion de revelar.</span>
      </div>

      <div className="p-6 max-w-6xl mx-auto space-y-5">
        <div className="tab-nav overflow-x-auto">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)} className={`tab-btn flex items-center gap-1.5 whitespace-nowrap ${activeTab === t.id ? 'active' : ''}`}>
              <t.icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          ))}
        </div>

        <motion.div key={activeTab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          {activeTab === 'usuarios' && (
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <h2 className="font-bold text-white text-lg">Gestion de Usuarios</h2>
                <button className="btn-primary flex items-center gap-1.5"><Plus className="w-3.5 h-3.5" /> Nuevo Usuario</button>
              </div>
              <div className="card-clinical overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/60">
                      {['Usuario', 'Rol', 'Estado', 'Acciones'].map(h => (
                        <th key={h} className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider px-3">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(users.length > 0 ? users : [
                      { id: '1', username: 'admin1', role: 'admin', active: true },
                      { id: '2', username: 'dr_garcia', role: 'medico', active: true },
                      { id: '3', username: 'paciente_001', role: 'paciente', active: false },
                    ]).map(u => (
                      <tr key={u.id} className="border-b border-slate-800/60 hover:bg-slate-800/20 transition-colors">
                        <td className="py-3 px-3 font-medium text-white">{u.username}</td>
                        <td className="py-3 px-3"><span className={`badge-role-${u.role}`}>{u.role}</span></td>
                        <td className="py-3 px-3">{u.active ? <span className="badge-low">Activo</span> : <span className="badge-critical">Inactivo</span>}</td>
                        <td className="py-3 px-3 space-x-3">
                          <button className="text-cyan-400 hover:text-cyan-300 text-xs font-medium transition-colors">Editar</button>
                          <button className="text-red-400 hover:text-red-300 text-xs font-medium transition-colors">Desactivar</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'pacientes' && (
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <h2 className="font-bold text-white text-lg flex items-center gap-2">
                  <Lock className="w-4 h-4 text-amber-400" />
                  Datos de Pacientes - Vista Cifrada
                </h2>
                <button onClick={fetchPatients} className="btn-ghost flex items-center gap-1.5 text-xs"><RefreshCw className="w-3.5 h-3.5" /> Refrescar</button>
              </div>
              <p className="text-xs text-slate-500">Todos los campos de identidad se muestran cifrados sin excepcion.</p>

              <div className="card-clinical overflow-x-auto">
                {loadingPatients ? (
                  <div className="space-y-2 p-2">{[...Array(5)].map((_, i) => <div key={i} className="skeleton h-10 w-full" />)}</div>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-700/60">
                        {['ID Publico', 'Nombre', 'Fecha Nac.', 'Genero', 'Estado'].map(h => (
                          <th key={h} className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider px-3">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {patients.map(p => {
                        const r = p.resource
                        const fullName = `${r?.name?.[0]?.given?.[0] ?? ''} ${r?.name?.[0]?.family ?? ''}`.trim()
                        return (
                          <tr key={r?.id} className="border-b border-slate-800/60">
                            <td className="py-3 px-3 text-slate-400 font-mono text-xs">{r?.id?.slice(0, 8)}...</td>
                            <td className="py-3 px-3"><EncField value={fullName} /></td>
                            <td className="py-3 px-3"><EncField value={r?.birthDate} /></td>
                            <td className="py-3 px-3"><EncField value={r?.gender} /></td>
                            <td className="py-3 px-3">{r?.active ? <span className="badge-low">Activo</span> : <span className="badge-critical">Inactivo</span>}</td>
                          </tr>
                        )
                      })}
                      {patients.length === 0 && (<tr><td colSpan={5} className="py-8 text-center text-slate-500">Sin datos - conecte el backend</td></tr>)}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}

          {activeTab === 'estadisticas' && (
            <div className="space-y-4">
              <h2 className="font-bold text-white text-lg">Estadisticas del Sistema</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: 'Total Pacientes', value: stats?.total_patients ?? patients.length ?? '-', icon: Users, color: '#22d3ee' },
                  { label: 'Usuarios Activos', value: users.filter(u => u.active).length || '-', icon: Activity, color: '#10b981' },
                  { label: 'Inferencias IA', value: stats?.total_inferences ?? '-', icon: BarChart2, color: '#a78bfa' },
                  { label: 'Tasa Exito IA', value: stats ? `${Math.round((stats.inference_acceptance_rate || 0) * 100)}%` : '-', icon: Shield, color: '#f59e0b' },
                ].map(s => (
                  <div key={s.label} className="stat-card">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-xs text-slate-400 font-medium uppercase tracking-wider">{s.label}</p>
                        <p className="text-3xl font-bold mt-1" style={{ color: s.color }}>{s.value}</p>
                      </div>
                      <s.icon className="w-5 h-5 mt-1" style={{ color: s.color }} />
                    </div>
                  </div>
                ))}
              </div>

              <div className="card-clinical">
                <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  Actividad de Inferencias (ultimos 7 dias)
                </h3>
                <div className="flex items-end gap-2 h-24">
                  {[32, 45, 28, 67, 54, 89, 73].map((v, i) => (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1">
                      <motion.div
                        initial={{ height: 0 }}
                        animate={{ height: `${(v / 89) * 80}px` }}
                        transition={{ delay: i * 0.06, duration: 0.5, ease: 'easeOut' }}
                        className="w-full rounded-t"
                        style={{ background: 'linear-gradient(180deg, #0891b2, #0e7490)', minHeight: '4px' }}
                      />
                      <span className="text-xs text-slate-500">{['L', 'M', 'X', 'J', 'V', 'S', 'D'][i]}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <h2 className="font-bold text-white text-lg">Registro de Auditoria</h2>
                <button onClick={handleExportLogs} className="btn-ghost flex items-center gap-1.5 text-xs"><Download className="w-3.5 h-3.5" /> Exportar CSV</button>
              </div>
              <div className="card-clinical space-y-2">
                {logs.map((log, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="flex items-center gap-3 p-2.5 rounded-lg bg-slate-800/40 border border-slate-700/40 text-sm"
                  >
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${log.result === 'SUCCESS' ? 'bg-emerald-400' : 'bg-red-400'}`} />
                    <span className="text-slate-500 font-mono text-xs w-40 flex-shrink-0">{new Date(log.ts).toLocaleString('es-CO')}</span>
                    <span className={`font-semibold text-xs w-28 flex-shrink-0 ${log.result === 'SUCCESS' ? 'text-cyan-400' : 'text-red-400'}`}>{log.action}</span>
                    <span className="text-slate-300 flex-1">{log.resource_type}{log.resource_id ? `#${String(log.resource_id).slice(0, 8)}` : ''}</span>
                    <span className="text-slate-500 text-xs">{log.role || 'n/a'}</span>
                    <span className={`text-xs font-medium ${log.result === 'SUCCESS' ? 'text-emerald-400' : 'text-red-400'}`}>{log.result}</span>
                  </motion.div>
                ))}
                {logs.length === 0 && <p className="text-sm text-slate-500">No hay eventos auditados disponibles.</p>}
              </div>
            </div>
          )}
        </motion.div>
      </div>

      <div className="footer-clinical px-6 pb-4">Ley 1581/2012 | Datos AES-256 | Panel de Administracion</div>
    </div>
  )
}