import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import { Eye, EyeOff, Stethoscope, ShieldCheck, Activity } from 'lucide-react'
import HabeasDataModal from '../components/HabeasDataModal'

/* ECG path that looks like a real heartbeat trace */
const ECG_PATH =
  'M0,50 L60,50 L75,50 L82,15 L89,85 L96,50 L103,50 L110,50 L117,30 L124,70 L131,50 L200,50 L260,50 L267,10 L274,90 L281,50 L350,50 L410,50 L417,20 L424,80 L431,50 L500,50'

const ROLES = [
  { value: 'medico',   label: 'Medico',        icon: 'M', desc: 'Acceso a historial clinico completo' },
  { value: 'paciente', label: 'Paciente',      icon: 'P', desc: 'Acceso a tus propios datos' },
  { value: 'admin',    label: 'Administrador', icon: 'A', desc: 'Panel de gestion y auditoria' },
]

function normalizeAccessKey(raw) {
  return String(raw || '')
    .replace(/[\u200B-\u200D\uFEFF]/g, '')
    .trim()
    .replace(/^[`"'“”‘’]+/, '')
    .replace(/[`"'“”‘’]+$/, '')
}

export default function Login() {
  const navigate = useNavigate()
  const [accessKey, setAccessKey] = useState('')
  const [permissionKey, setPermissionKey] = useState('medico')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [habeasAccepted, setHabeasAccepted] = useState(false)

  const selectedRole = ROLES.find(r => r.value === permissionKey)

  const handleLogin = async (e) => {
    e.preventDefault()
    if (!habeasAccepted) {
      toast.error('Debe aceptar la politica de Habeas Data')
      return
    }
    setLoading(true)
    try {
      const cleanAccessKey = normalizeAccessKey(accessKey)
      if (!cleanAccessKey) {
        toast.error('La Access Key esta vacia o tiene caracteres invalidos')
        setLoading(false)
        return
      }
      if (cleanAccessKey !== accessKey) {
        setAccessKey(cleanAccessKey)
      }
      const payload = JSON.stringify({ access_key: cleanAccessKey, permission_key: permissionKey })
      const requestConfig = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
      }

      let response = await fetch('/auth/login', requestConfig)

      // If reverse proxy is temporarily unavailable, retry direct backend in local dev.
      if (!response.ok && response.status >= 500 && window.location.hostname === 'localhost') {
        response = await fetch('http://localhost:8000/auth/login', requestConfig)
      }

      if (response.ok) {
        const data = await response.json()
        sessionStorage.setItem('token', data.access_token)
        sessionStorage.setItem('role', data.role)
        sessionStorage.setItem('accessKey', cleanAccessKey)
        sessionStorage.setItem('permissionKey', permissionKey)
        toast.success('Autenticacion exitosa')
        navigate('/dashboard')
      } else {
        let message = 'Credenciales invalidas'
        try {
          const isJson = (response.headers.get('content-type') || '').includes('application/json')
          const err = isJson ? await response.json() : {}
          const detail = String(err?.detail || '').toLowerCase()
          if (detail.includes('permission key mismatch')) {
            message = 'La clave es valida, pero el rol seleccionado no coincide'
          } else if (detail.includes('invalid credentials') || detail.includes('invalid or inactive api key')) {
            message = 'Access Key invalida o inactiva'
          } else if (response.status >= 500) {
            message = 'Error temporal del servidor/proxy. Intenta nuevamente en unos segundos.'
          } else if (response.status === 400) {
            message = 'Solicitud invalida: verifica Access Key y rol'
          } else if (response.status === 401 || response.status === 403) {
            message = 'Credenciales no validas para el rol seleccionado'
          } else if (err?.detail) {
            message = String(err.detail)
          }
        } catch {
          if (response.status >= 500) {
            message = 'Error temporal del servidor/proxy. Intenta nuevamente en unos segundos.'
          }
        }
        toast.error(message)
      }
    } catch {
      toast.error('Error de conexion al servidor')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      <HabeasDataModal onAccept={() => setHabeasAccepted(true)} />

      {/* Animated background grid */}
      <div className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: 'linear-gradient(rgba(6,182,212,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.03) 1px, transparent 1px)',
          backgroundSize: '40px 40px'
        }}
      />

      {/* ECG strips */}
      {[0, 1, 2].map(i => (
        <div key={i} className="absolute w-full overflow-hidden opacity-20 pointer-events-none"
          style={{ top: `${20 + i * 30}%` }}>
          <svg viewBox="0 0 500 100" preserveAspectRatio="none"
            style={{ width: '100%', height: '60px' }}>
            <path d={ECG_PATH} fill="none" stroke="#22d3ee" strokeWidth="1.5"
              strokeLinecap="round"
              style={{
                strokeDasharray: 1200,
                strokeDashoffset: 0,
                animation: `ecg-draw ${2.5 + i * 0.7}s ease-in-out infinite`,
                animationDelay: `${i * 0.8}s`
              }} />
          </svg>
        </div>
      ))}

      {/* Glow blobs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full pointer-events-none"
        style={{ background: 'radial-gradient(circle, rgba(8,145,178,0.08) 0%, transparent 70%)' }} />
      <div className="absolute bottom-1/4 right-1/4 w-80 h-80 rounded-full pointer-events-none"
        style={{ background: 'radial-gradient(circle, rgba(16,185,129,0.06) 0%, transparent 70%)' }} />

      {/* Card */}
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="w-full max-w-md relative z-10"
      >
        <div className="glass-effect rounded-2xl p-8">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="relative inline-flex items-center justify-center w-16 h-16 mb-4">
              <div className="absolute inset-0 rounded-full bg-cyan-500/10 pulse-ring" />
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-cyan-600/30 to-teal-600/20 border border-cyan-500/30 flex items-center justify-center">
                <Activity className="w-8 h-8 text-cyan-400" />
              </div>
            </div>
            <h1 className="text-2xl font-bold text-white mb-1">
              <span className="gradient-text">BioMed</span>
              <span className="text-white"> Clinical</span>
            </h1>
            <p className="text-slate-400 text-sm">Sistema Clinico Digital · HL7 FHIR R4</p>

            {/* Habeas Data indicator */}
            <div className={`mt-3 inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full transition-all ${
              habeasAccepted
                ? 'bg-emerald-900/30 text-emerald-400 border border-emerald-700/50'
                : 'bg-amber-900/30 text-amber-400 border border-amber-700/50'
            }`}>
              <ShieldCheck className="w-3 h-3" />
              {habeasAccepted ? 'Habeas Data aceptado' : 'Pendiente aceptar Habeas Data'}
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleLogin} className="space-y-5">
            {/* Role Selector */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Tipo de Acceso
              </label>
              <div className="grid grid-cols-3 gap-2">
                {ROLES.map(role => (
                  <button
                    key={role.value}
                    type="button"
                    onClick={() => setPermissionKey(role.value)}
                    className={`p-2.5 rounded-lg border text-center transition-all ${
                      permissionKey === role.value
                        ? 'bg-cyan-900/30 border-cyan-500/60 text-cyan-300'
                        : 'bg-slate-800/40 border-slate-700/60 text-slate-400 hover:border-slate-600'
                    }`}
                  >
                    <div className="text-xl mb-0.5">{role.icon}</div>
                    <div className="text-xs font-semibold">{role.label}</div>
                  </button>
                ))}
              </div>
              {selectedRole && (
                <p className="text-xs text-slate-500 mt-1.5 text-center">{selectedRole.desc}</p>
              )}
              <p className="text-xs text-amber-400/90 mt-1.5 text-center">
                El Access Key debe coincidir con el rol seleccionado.
              </p>
            </div>

            {/* Access Key */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Clave de Acceso
              </label>
              <div className="relative">
                <Stethoscope className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={accessKey}
                  onChange={e => setAccessKey(e.target.value)}
                  placeholder="Ingrese su clave de acceso"
                  className="input-clinical pl-9 pr-10"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <motion.button
              type="submit"
              disabled={loading}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="w-full py-3 rounded-lg font-semibold text-white transition-all relative overflow-hidden disabled:opacity-50"
              style={{ background: 'linear-gradient(135deg, #0891b2, #0e7490)', boxShadow: '0 0 20px rgba(8,145,178,0.4)' }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                  </svg>
                  Autenticando...
                </span>
              ) : (
                'Ingresar al Sistema'
              )}
            </motion.button>
          </form>

          {/* Footer */}
          <p className="text-center text-xs text-slate-600 mt-6">
            Protegido · Ley 1581/2012 · Datos AES-256 · Universidad Autonoma de Occidente
          </p>
        </div>
      </motion.div>
    </div>
  )
}

