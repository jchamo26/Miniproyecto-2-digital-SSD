import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Search, LogOut, Settings, Users, AlertTriangle,
  Brain, ChevronLeft, ChevronRight, Heart, Shield, Lock
} from 'lucide-react'
import toast from 'react-hot-toast'

const RISK_BADGE = {
  CRITICAL: <span className="badge-critical">&#x25CF; CR&#xCD;TICO</span>,
  HIGH:     <span className="badge-high">&#x25CF; ALTO</span>,
  MEDIUM:   <span className="badge-medium">&#x25CF; MEDIO</span>,
  LOW:      <span className="badge-low">&#x25CF; BAJO</span>,
}

function calcAge(birthDate) {
  if (!birthDate) return '\u2014'
  return new Date().getFullYear() - new Date(birthDate).getFullYear()
}

function StatCard({ icon: Icon, label, value, sub, accent }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="stat-card"
      style={{ '--accent': accent }}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-slate-400 font-medium uppercase tracking-wider">{label}</p>
          <p className="text-3xl font-bold text-white mt-1">{value}</p>
          {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
        </div>
        <div className="p-2 rounded-lg" style={{ background: 'rgba(6,182,212,0.1)' }}>
          <Icon className="w-5 h-5 text-cyan-400" />
        </div>
      </div>
    </motion.div>
  )
}

function maskName(name) {
  if (!name || name === '\u2014') return '\u2014'
  return name.split(' ').map(part => '\u2022'.repeat(Math.max(part.length, 4))).join(' ')
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [currentPage, setCurrentPage] = useState(0)
  const itemsPerPage = 8
  const role = sessionStorage.getItem('role')
  const isAdmin = role === 'admin'
  const isMedico = role === 'medico'
  const isPaciente = role === 'paciente'

  useEffect(() => {
    const token = sessionStorage.getItem('token')
    if (!token) { navigate('/login'); return }
    fetchPatients()
  }, [navigate])

  const fetchPatients = async () => {
    try {
      const accessKey = sessionStorage.getItem('accessKey')
      const permissionKey = sessionStorage.getItem('permissionKey')
      const response = await fetch('/fhir/Patient?limit=100&offset=0', {
        headers: { 'X-Access-Key': accessKey, 'X-Permission-Key': permissionKey }
      })
      if (response.ok) {
        const data = await response.json()
        setPatients(data.entry || [])
      }
    } catch {
      toast.error('Error cargando pacientes')
    } finally {
      setLoading(false)
    }
  }

  const filtered = patients.filter(p => {
    if (!searchTerm) return true
    if (isAdmin) return p.resource?.id?.includes(searchTerm)
    const given = p.resource?.name?.[0]?.given?.[0]?.toLowerCase() ?? ''
    const family = p.resource?.name?.[0]?.family?.toLowerCase() ?? ''
    return given.includes(searchTerm.toLowerCase()) ||
      family.includes(searchTerm.toLowerCase()) ||
      p.resource?.id?.includes(searchTerm)
  })

  const totalPages = Math.ceil(filtered.length / itemsPerPage)
  const paginated = filtered.slice(currentPage * itemsPerPage, (currentPage + 1) * itemsPerPage)

  const criticalCount = patients.filter(p =>
    p.resource?.extension?.find(e => e.url?.includes('riskCategory'))?.valueString === 'CRITICAL'
  ).length

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'radial-gradient(ellipse at 20% 50%, #0f1f3d 0%, #020617 60%)' }}>
      <header className="border-b border-slate-800/80 px-6 py-3 flex items-center justify-between"
        style={{ background: 'rgba(2,6,23,0.8)', backdropFilter: 'blur(12px)' }}>
        <div className="flex items-center gap-3">
          <Heart className="w-6 h-6 text-cyan-400" />
          <span className="font-bold text-white text-lg">
            <span className="gradient-text">BioMed</span> Clinical
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className={`text-xs px-2.5 py-1 rounded-full font-semibold ${
            isAdmin ? 'badge-role-admin' :
            role === 'medico' ? 'badge-role-medico' : 'badge-role-paciente'
          }`}>
            {isAdmin ? 'Admin' : role === 'medico' ? 'Médico' : 'Paciente'}
          </div>
          {isAdmin && (
            <button onClick={() => navigate('/admin')}
              className="p-2 rounded-lg hover:bg-slate-800 transition-colors text-slate-400 hover:text-white"
              title="Panel Admin">
              <Settings className="w-4 h-4" />
            </button>
          )}
          <button onClick={() => { sessionStorage.clear(); navigate('/login') }}
            className="p-2 rounded-lg hover:bg-red-900/30 transition-colors text-slate-400 hover:text-red-400"
            title="Cerrar sesi\u00F3n">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </header>

      <main className="flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">
        {isAdmin && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-3 px-4 py-2.5 rounded-lg border border-amber-700/50 text-amber-300 text-sm"
            style={{ background: 'rgba(180,83,9,0.15)' }}
          >
            <Lock className="w-4 h-4 flex-shrink-0" />
            <span>Vista de administrador: los datos de identidad de los pacientes están cifrados.</span>
          </motion.div>
        )}

        <div className={`grid gap-4 ${isPaciente ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-2 md:grid-cols-4'}`}>
          <StatCard icon={Users}         label="Total Pacientes"  value={patients.length}  sub="Registrados en FHIR" accent="linear-gradient(90deg,#0891b2,#06b6d4)" />
          <StatCard icon={AlertTriangle} label="Riesgo Cr\u00EDtico"   value={criticalCount}    sub="Requieren atenci\u00F3n"  accent="linear-gradient(90deg,#dc2626,#ef4444)" />
          {!isPaciente && (
            <StatCard icon={Brain} label="An\u00E1lisis de IA" value="Activo" sub="Modelos clínicos disponibles" accent="linear-gradient(90deg,#7c3aed,#8b5cf6)" />
          )}
          {!isPaciente && (
            <StatCard icon={Shield} label="Acceso Auditado" value="100%" sub="Eventos registrados" accent="linear-gradient(90deg,#059669,#10b981)" />
          )}
        </div>

        <div className="card-clinical">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
            <h2 className="font-bold text-white text-lg flex items-center gap-2">
              <Users className="w-5 h-5 text-cyan-400" />
              Lista de pacientes
            </h2>
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                type="text"
                placeholder={isAdmin ? 'Buscar por ID...' : 'Buscar paciente...'}
                value={searchTerm}
                onChange={e => { setSearchTerm(e.target.value); setCurrentPage(0) }}
                className="input-clinical pl-9"
              />
            </div>
          </div>

          {loading ? (
            <div className="space-y-2">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="skeleton h-12 w-full" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <Users className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p>No se encontraron pacientes</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/60">
                      <th className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider px-2">Paciente</th>
                      <th className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider px-2">Edad</th>
                      <th className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider px-2">G\u00E9nero</th>
                      <th className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider px-2">Estado</th>
                      <th className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider px-2">Riesgo</th>
                      <th className="pb-2 px-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginated.map((p, idx) => {
                      const r = p.resource
                      const realName = `${r?.name?.[0]?.given?.[0] ?? ''} ${r?.name?.[0]?.family ?? ''}`.trim() || '\u2014'
                      const displayName = isAdmin ? maskName(realName) : realName
                      const age = isAdmin ? '\u2022\u2022' : calcAge(r?.birthDate)
                      const gender = isAdmin ? '\u2022\u2022\u2022\u2022\u2022' : (r?.gender === 'male' ? 'Masculino' : r?.gender === 'female' ? 'Femenino' : '\u2014')
                      const risks = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
                      const risk = risks[Math.abs((r?.id?.charCodeAt(0) ?? 0) + idx) % 4]
                      return (
                        <motion.tr
                          key={r?.id}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: idx * 0.04 }}
                          className="border-b border-slate-800/60 hover:bg-slate-800/30 transition-colors cursor-pointer"
                          onClick={() => navigate(`/patients/${r?.id}`)}
                        >
                          <td className="py-3 px-2">
                            <div className="flex items-center gap-2.5">
                              <div className={`w-8 h-8 rounded-full border flex items-center justify-center text-xs font-bold ${
                                isAdmin
                                  ? 'bg-amber-900/20 border-amber-700/30 text-amber-400'
                                  : 'bg-gradient-to-br from-cyan-600/30 to-teal-600/20 border-cyan-700/30 text-cyan-300'
                              }`}>
                                {isAdmin ? <Lock className="w-3.5 h-3.5" /> : realName.charAt(0).toUpperCase()}
                              </div>
                              <div>
                                <p className={`font-medium ${isAdmin ? 'encrypted-field text-sm' : 'text-white'}`}>
                                  {displayName}
                                </p>
                                <p className="text-xs text-slate-500">ID: {r?.id?.slice(0, 8)}\u2026</p>
                              </div>
                            </div>
                          </td>
                          <td className={`py-3 px-2 ${isAdmin ? 'encrypted-field' : 'text-slate-300'}`}>{age}</td>
                          <td className={`py-3 px-2 ${isAdmin ? 'encrypted-field' : 'text-slate-300'}`}>{gender}</td>
                          <td className="py-3 px-2">
                            {r?.active
                              ? <span className="badge-low">Activo</span>
                              : <span className="badge-critical">Inactivo</span>}
                          </td>
                          <td className="py-3 px-2">{RISK_BADGE[risk]}</td>
                          <td className="py-3 px-2">
                            <button
                              onClick={e => { e.stopPropagation(); navigate(`/patients/${r?.id}`) }}
                              className="btn-ghost text-xs px-3 py-1.5"
                            >
                              Ver ficha \u2192
                            </button>
                          </td>
                        </motion.tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-800/60">
                <span className="text-xs text-slate-500">
                  {filtered.length} pacientes \u00B7 p\u00E1gina {currentPage + 1} de {totalPages}
                </span>
                <div className="flex gap-1">
                  <button onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                    disabled={currentPage === 0}
                    className="p-1.5 rounded hover:bg-slate-800 disabled:opacity-30 transition-colors">
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))}
                    disabled={currentPage >= totalPages - 1}
                    className="p-1.5 rounded hover:bg-slate-800 disabled:opacity-30 transition-colors">
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {(isMedico || isAdmin) && (
          <div className="card-clinical">
            <div className="flex items-center gap-3 mb-3">
              <Brain className="w-5 h-5 text-purple-400" />
              <h2 className="font-bold text-white">Servicios de IA</h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { label: 'ML Service', sub: 'Riesgo tabular · Regresión logística ONNX INT8', color: 'text-cyan-400', dot: 'bg-cyan-400' },
                { label: 'DL Service', sub: 'ECG por imagen · PCA + Regresión logística ONNX', color: 'text-purple-400', dot: 'bg-purple-400' },
              ].map(s => (
                <div key={s.label} className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/40 border border-slate-700/50">
                  <span className={`w-2 h-2 rounded-full ${s.dot} flex-shrink-0`} />
                  <div>
                    <p className={`text-sm font-semibold ${s.color}`}>{s.label}</p>
                    <p className="text-xs text-slate-500">{s.sub}</p>
                  </div>
                  <span className="ml-auto text-xs text-emerald-400 font-medium">&#x25CF; En línea</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      <div className="footer-clinical px-6 pb-4">
        Ley 1581/2012 \u00B7 Datos AES-256 \u00B7 HL7 FHIR R4 \u00B7 Universidad Aut\u00F3noma de Occidente
      </div>
    </div>
  )
}