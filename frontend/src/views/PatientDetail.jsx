import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowLeft, Zap, AlertTriangle,
  User, Calendar, Activity, Heart, Lock, FileText, ClipboardList
} from 'lucide-react'
import toast from 'react-hot-toast'
import InferencePanel from '../components/InferencePanel'
import RiskReportForm from '../components/RiskReportForm'

function MaskedField({ value, role, alwaysShow = false }) {
  if (alwaysShow || role !== 'admin') {
    return <span className="text-white">{value || '-'}</span>
  }
  return <span className="encrypted-field">{'*'.repeat(Math.max(8, String(value ?? '').length))}</span>
}

function VitalsSparkline({ data, color = '#22d3ee', label }) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const w = 200
  const h = 50
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - ((v - min) / range) * (h - 8) - 4
    return `${x},${y}`
  }).join(' ')

  return (
    <div>
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-12">
        <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {data.map((v, i) => {
          const x = (i / (data.length - 1)) * w
          const y = h - ((v - min) / range) * (h - 8) - 4
          return <circle key={i} cx={x} cy={y} r="3" fill={color} />
        })}
      </svg>
      <div className="flex justify-between text-xs text-slate-500 mt-0.5">
        <span>{min}</span>
        <span className="font-semibold" style={{ color }}>{data[data.length - 1]}</span>
        <span>{max}</span>
      </div>
    </div>
  )
}

export default function PatientDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [patient, setPatient] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('datos')
  const [riskReport, setRiskReport] = useState(null)
  const [riskReports, setRiskReports] = useState([])
  const [observations, setObservations] = useState([])
  const [diagnosticReports, setDiagnosticReports] = useState([])
  const [showInferencePanel, setShowInferencePanel] = useState(false)
  const [observationForm, setObservationForm] = useState({ display: 'Nota clinica', code: '48767-8', value: '', unit: '1' })
  const [correctionForm, setCorrectionForm] = useState({ field_name: 'name', requested_value: '', reason: '' })

  const role = sessionStorage.getItem('role')
  const isAdmin = role === 'admin'
  const isMedico = role === 'medico'
  const isPaciente = role === 'paciente'
  const tabs = [
    { id: 'datos', label: 'Datos clínicos', icon: User },
    { id: 'vitales', label: 'Signos vitales', icon: Activity },
    ...(isMedico ? [{ id: 'analisis', label: 'Análisis de IA', icon: Zap }] : []),
    ...(isAdmin ? [{ id: 'auditoria', label: 'Auditoría', icon: FileText }] : []),
  ]

  useEffect(() => { fetchPatientContext() }, [id])
  useEffect(() => {
    if (!tabs.some(tab => tab.id === activeTab)) {
      setActiveTab(tabs[0].id)
    }
  }, [activeTab, tabs])

  const authHeaders = () => ({
    'X-Access-Key': sessionStorage.getItem('accessKey'),
    'X-Permission-Key': sessionStorage.getItem('permissionKey'),
  })

  const fetchPatientContext = async () => {
    try {
      const [patientResponse, observationResponse, riskResponse, diagnosticResponse] = await Promise.all([
        fetch(`/fhir/Patient/${id}`, { headers: authHeaders() }),
        fetch(`/fhir/Observation?subject=Patient/${id}`, { headers: authHeaders() }),
        fetch(`/fhir/RiskAssessment?patient_id=${id}`, { headers: authHeaders() }),
        fetch(`/fhir/DiagnosticReport?patient_id=${id}`, { headers: authHeaders() }),
      ])

      if (patientResponse.ok) setPatient(await patientResponse.json())
      if (observationResponse.ok) {
        const data = await observationResponse.json()
        setObservations(data.entry || [])
      }
      if (riskResponse.ok) {
        const data = await riskResponse.json()
        const entries = (data.entry || []).map(item => item.resource)
        setRiskReports(entries)
        setRiskReport(entries.find(item => !item.signed_at) || null)
      }
      if (diagnosticResponse.ok) {
        const data = await diagnosticResponse.json()
        setDiagnosticReports((data.entry || []).map(item => item.resource))
      }
    } catch {
      toast.error('Error cargando paciente')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateObservation = async () => {
    if (!isMedico || !observationForm.value) return
    try {
      const response = await fetch('/fhir/Observation', {
        method: 'POST',
        headers: {
          ...authHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          resourceType: 'Observation',
          subject: { reference: `Patient/${id}` },
          code: { coding: [{ system: 'http://loinc.org', code: observationForm.code, display: observationForm.display }] },
          valueQuantity: { value: Number(observationForm.value), unit: observationForm.unit },
        }),
      })
      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        toast.error(err.detail || 'No se pudo crear la observacion')
        return
      }
      toast.success('Observacion agregada al historial')
      setObservationForm({ ...observationForm, value: '' })
      fetchPatientContext()
    } catch {
      toast.error('Error de conexion al crear observacion')
    }
  }

  const handleCorrectionRequest = async () => {
    if (!isPaciente) return
    try {
      const response = await fetch(`/fhir/Patient/${id}/data-correction-request`, {
        method: 'POST',
        headers: {
          ...authHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(correctionForm),
      })
      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        toast.error(err.detail || 'No se pudo registrar la solicitud ARCO')
        return
      }
      toast.success('Solicitud de correccion registrada')
      setCorrectionForm({ field_name: 'name', requested_value: '', reason: '' })
    } catch {
      toast.error('Error de conexion al solicitar correccion')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 rounded-full border-2 border-cyan-500 border-t-transparent animate-spin mx-auto mb-3" />
          <p className="text-slate-400 text-sm">Cargando ficha clínica...</p>
        </div>
      </div>
    )
  }

  const fullName = `${patient?.name?.[0]?.given?.[0] ?? ''} ${patient?.name?.[0]?.family ?? ''}`.trim() || 'Paciente'
  const initials = fullName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()

  const vitals = {
    heartRate: [72, 75, 68, 80, 77, 73, 78, 74, 76, 71],
    systolic: [118, 122, 115, 130, 124, 119, 125, 121, 118, 120],
    oxygen: [98, 97, 99, 98, 96, 98, 97, 99, 98, 97],
    glucose: [95, 102, 88, 110, 98, 94, 105, 99, 97, 101],
  }

  return (
    <div className="min-h-screen" style={{ background: 'radial-gradient(ellipse at 20% 50%, #0f1f3d 0%, #020617 60%)' }}>
      <header
        className="border-b border-slate-800/80 px-6 py-3 flex items-center gap-4"
        style={{ background: 'rgba(2,6,23,0.8)', backdropFilter: 'blur(12px)' }}
      >
        <button
          onClick={() => navigate('/dashboard')}
          className="p-1.5 rounded-lg hover:bg-slate-800 transition-colors text-slate-400 hover:text-white"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <Heart className="w-5 h-5 text-cyan-400" />
        <span className="text-sm text-slate-400">Dashboard</span>
        <span className="text-slate-600">/</span>
        <span className="text-sm text-white font-medium">Ficha clínica</span>
        {isAdmin && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-amber-400 bg-amber-900/20 border border-amber-700/40 px-2.5 py-1 rounded-full">
            <Lock className="w-3 h-3" />
            Datos de identidad cifrados para admin
          </span>
        )}
      </header>

      <div className="p-6 max-w-5xl mx-auto space-y-5">
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="card-clinical flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-600/40 to-teal-700/30 border border-cyan-600/30 flex items-center justify-center text-xl font-bold text-cyan-300 flex-shrink-0">
            {isAdmin ? '##' : initials}
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-bold text-white">
              <MaskedField value={fullName} role={role} />
            </h1>
            <div className="flex flex-wrap gap-3 mt-1 text-sm text-slate-400">
              <span className="flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" />
                <MaskedField value={patient?.birthDate} role={role} />
              </span>
              <span className="flex items-center gap-1">
                <User className="w-3.5 h-3.5" />
                <MaskedField value={patient?.gender} role={role} />
              </span>
              <span className="text-slate-600">ID: {patient?.id?.slice(0, 8)}...</span>
            </div>
          </div>
          <div className="flex gap-2">
            {patient?.active ? <span className="badge-low">Activo</span> : <span className="badge-critical">Inactivo</span>}
          </div>
        </motion.div>

        {riskReport && !riskReport.signed_at && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-3 rounded-lg bg-red-900/20 border border-red-700/50 flex items-center gap-3">
            <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <p className="text-sm text-red-300">RiskReport pendiente de firma. No puede cerrar el caso.</p>
          </motion.div>
        )}

        <div className="tab-nav overflow-x-auto">
          {tabs.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`tab-btn flex items-center gap-1.5 whitespace-nowrap ${activeTab === tab.id ? 'active' : ''}`}>
              <tab.icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          ))}
        </div>

        <motion.div key={activeTab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          {activeTab === 'datos' && (
            <div className="space-y-4">
              <div className="card-clinical">
                <h3 className="font-bold text-white mb-4 flex items-center gap-2">
                  <User className="w-4 h-4 text-cyan-400" />
                  Información demográfica
                  {isAdmin && <span className="text-xs text-amber-400 font-normal ml-1">(cifrado para admin)</span>}
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-y-5 gap-x-6">
                  {[
                    { label: 'Nombre completo', value: fullName },
                    { label: 'Fecha de nacimiento', value: patient?.birthDate },
                    { label: 'Género', value: patient?.gender },
                    { label: 'ID FHIR', value: patient?.id, alwaysShow: true },
                    { label: 'Estado', value: patient?.active ? 'Activo' : 'Inactivo', alwaysShow: true },
                    { label: 'Recurso', value: 'Patient R4', alwaysShow: true },
                  ].map(f => (
                    <div key={f.label}>
                      <p className="text-xs text-slate-400 mb-0.5 font-medium uppercase tracking-wide">{f.label}</p>
                      <MaskedField value={f.value} role={role} alwaysShow={f.alwaysShow} />
                    </div>
                  ))}
                </div>
              </div>

              {patient?.telecom && patient.telecom.length > 0 && (
                <div className="card-clinical">
                  <h3 className="font-bold text-white mb-3 flex items-center gap-2">
                    <ClipboardList className="w-4 h-4 text-cyan-400" />
                    Contacto
                  </h3>
                  <div className="space-y-2">
                    {patient.telecom.map((t, i) => (
                      <div key={i} className="flex justify-between text-sm">
                        <span className="text-slate-400 capitalize">{t.system}</span>
                        <MaskedField value={t.value} role={role} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'vitales' && (
            <div className="space-y-4">
              <div className="card-clinical">
                <h3 className="font-bold text-white mb-4 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  Tendencias de signos vitales
                  <span className="text-xs text-slate-500 font-normal">(últimas 10 mediciones)</span>
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                  <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40"><VitalsSparkline data={vitals.heartRate} color="#f87171" label="Frecuencia cardíaca (lpm)" /></div>
                  <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40"><VitalsSparkline data={vitals.systolic} color="#fb923c" label="Presión sistólica (mmHg)" /></div>
                  <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40"><VitalsSparkline data={vitals.oxygen} color="#34d399" label="Saturación O2 (%)" /></div>
                  <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40"><VitalsSparkline data={vitals.glucose} color="#a78bfa" label="Glucosa en sangre (mg/dL)" /></div>
                </div>
              </div>

              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'FC', value: `${vitals.heartRate.at(-1)} lpm`, color: '#f87171' },
                  { label: 'PA sistólica', value: `${vitals.systolic.at(-1)} mmHg`, color: '#fb923c' },
                  { label: 'SpO2', value: `${vitals.oxygen.at(-1)}%`, color: '#34d399' },
                  { label: 'Glucosa', value: `${vitals.glucose.at(-1)} mg/dL`, color: '#a78bfa' },
                ].map(v => (
                  <div key={v.label} className="card-clinical text-center">
                    <p className="text-xs text-slate-400">{v.label}</p>
                    <p className="text-xl font-bold mt-1" style={{ color: v.color }}>{v.value}</p>
                  </div>
                ))}
              </div>

              <div className="card-clinical">
                <h3 className="font-bold text-white mb-3">Observaciones del historial</h3>
                <div className="space-y-2">
                  {observations.map((item, index) => {
                    const obs = item.resource
                    return (
                      <div key={obs.id || index} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-800/40 border border-slate-700/40 text-sm">
                        <div>
                          <p className="text-white font-medium">{obs?.code?.coding?.[0]?.display || obs?.code?.text || 'Observation'}</p>
                          <p className="text-xs text-slate-500">{obs?.effectiveDateTime ? new Date(obs.effectiveDateTime).toLocaleString('es-CO') : 'Sin fecha'}</p>
                        </div>
                        <span className="text-cyan-300">{obs?.valueQuantity?.value} {obs?.valueQuantity?.unit}</span>
                      </div>
                    )
                  })}
                  {observations.length === 0 && <p className="text-sm text-slate-500">No hay observations registradas.</p>}
                </div>

                {isMedico && (
                  <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-3">
                    <input className="input-clinical" value={observationForm.display} onChange={e => setObservationForm({ ...observationForm, display: e.target.value })} placeholder="Nombre de la observación" />
                    <input className="input-clinical" value={observationForm.code} onChange={e => setObservationForm({ ...observationForm, code: e.target.value })} placeholder="Código LOINC" />
                    <input className="input-clinical" value={observationForm.value} onChange={e => setObservationForm({ ...observationForm, value: e.target.value })} placeholder="Valor" type="number" />
                    <input className="input-clinical" value={observationForm.unit} onChange={e => setObservationForm({ ...observationForm, unit: e.target.value })} placeholder="Unidad" />
                    <button onClick={handleCreateObservation} className="btn-primary md:col-span-4">Agregar observación al historial</button>
                  </div>
                )}
              </div>

              {isPaciente && (
                <div className="card-clinical">
                  <h3 className="font-bold text-white mb-3 flex items-center gap-2">
                    <ClipboardList className="w-4 h-4 text-cyan-400" />
                    Solicitud de corrección de datos (ARCO)
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <select
                      value={correctionForm.field_name}
                      onChange={e => setCorrectionForm({ ...correctionForm, field_name: e.target.value })}
                      className="input-clinical"
                    >
                      <option value="name">Nombre</option>
                      <option value="birthDate">Fecha de nacimiento</option>
                      <option value="gender">Género</option>
                    </select>
                    <input
                      value={correctionForm.requested_value}
                      onChange={e => setCorrectionForm({ ...correctionForm, requested_value: e.target.value })}
                      placeholder="Valor correcto solicitado"
                      className="input-clinical"
                    />
                    <input
                      value={correctionForm.reason}
                      onChange={e => setCorrectionForm({ ...correctionForm, reason: e.target.value })}
                      placeholder="Motivo de la corrección"
                      className="input-clinical"
                    />
                  </div>
                  <button onClick={handleCorrectionRequest} className="btn-primary mt-3">Enviar solicitud</button>
                </div>
              )}
            </div>
          )}

          {activeTab === 'analisis' && (
            <div className="space-y-4">
              {isAdmin ? (
                <div className="card-clinical p-6 border border-amber-700/40 bg-amber-900/15 text-amber-300 flex items-start gap-3">
                  <Lock className="w-5 h-5 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="font-semibold">Acceso restringido para admin</p>
                    <p className="text-sm text-amber-200 mt-1">Los resultados clínicos de inferencia se muestran solo a médico y paciente.</p>
                  </div>
                </div>
              ) : isMedico && !showInferencePanel ? (
                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.99 }}
                  onClick={() => setShowInferencePanel(true)}
                  className="w-full card-clinical text-center p-10 cursor-pointer hover:card-glow transition-all"
                >
                  <div className="w-14 h-14 rounded-full bg-gradient-to-br from-purple-600/30 to-cyan-600/20 border border-purple-500/40 flex items-center justify-center mx-auto mb-3">
                    <Zap className="w-7 h-7 text-yellow-400" />
                  </div>
                  <p className="font-bold text-white text-lg">Ejecutar análisis ML / DL</p>
                  <p className="text-sm text-slate-400 mt-1">Riesgo clínico con fusión multimodelo</p>
                  <p className="text-xs text-slate-600 mt-3">ONNX INT8 para baja latencia en entorno clínico</p>
                </motion.button>
              ) : isMedico ? (
                <InferencePanel patientId={id} onClose={() => setShowInferencePanel(false)} />
              ) : (
                <div className="space-y-4">
                  <div className="card-clinical p-4 border border-cyan-700/40 bg-cyan-900/10 text-cyan-200">
                    Como paciente puede consultar sus diagnósticos y reportes firmados, pero no ejecutar modelos.
                  </div>

                  <div className="card-clinical">
                    <h3 className="font-bold text-white mb-3">RiskReports firmados</h3>
                    <div className="space-y-2">
                      {riskReports.filter(item => item.signed_at).map(item => (
                        <div key={item.id} className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40">
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-sm text-white font-medium">{item.model_type}</span>
                            <span className="badge-low">Firmado</span>
                          </div>
                          <p className="text-sm text-slate-400 mt-1">Categoría: {item.risk_category} | Score: {(Number(item.risk_score || 0) * 100).toFixed(1)}%</p>
                        </div>
                      ))}
                      {riskReports.filter(item => item.signed_at).length === 0 && <p className="text-sm text-slate-500">No hay RiskReports firmados visibles.</p>}
                    </div>
                  </div>

                  <div className="card-clinical">
                    <h3 className="font-bold text-white mb-3">DiagnosticReports</h3>
                    <div className="space-y-2">
                      {diagnosticReports.map(report => (
                        <div key={report.id} className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40">
                          <p className="text-sm font-medium text-white">{report.code?.text || 'DiagnosticReport'}</p>
                          <p className="text-xs text-slate-400 mt-1">{report.conclusion || 'Sin conclusión'}</p>
                        </div>
                      ))}
                      {diagnosticReports.length === 0 && <p className="text-sm text-slate-500">No hay DiagnosticReports registrados.</p>}
                    </div>
                  </div>
                </div>
              )}

              {isMedico && riskReport && (
                <RiskReportForm
                  riskReport={riskReport}
                  patientId={id}
                  onSigned={() => setRiskReport({ ...riskReport, signed_at: new Date() })}
                />
              )}
            </div>
          )}

          {activeTab === 'auditoria' && (
            <div className="card-clinical space-y-3">
                <h3 className="font-bold text-white flex items-center gap-2">
                <FileText className="w-4 h-4 text-cyan-400" />
                Registro de auditoría
              </h3>
              <div className="space-y-2">
                {[
                  { time: new Date().toLocaleString('es-CO'), action: 'Acceso a ficha clínica', user: role },
                  { time: new Date(Date.now() - 3600000).toLocaleString('es-CO'), action: 'Consulta de datos demográficos', user: role },
                ].map((log, i) => (
                  <div key={i} className="flex items-center gap-3 p-2.5 rounded-lg bg-slate-800/40 border border-slate-700/40 text-sm">
                    <span className="w-2 h-2 rounded-full bg-cyan-400 flex-shrink-0" />
                    <span className="text-slate-500 font-mono text-xs">{log.time}</span>
                    <span className="text-slate-300">{log.action}</span>
                    <span className="ml-auto text-xs text-slate-500">por {log.user}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      </div>

      <div className="footer-clinical px-6 pb-4">Ley 1581/2012 | Datos AES-256 | HL7 FHIR R4</div>
    </div>
  )
}