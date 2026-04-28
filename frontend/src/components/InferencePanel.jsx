import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Zap, Loader, AlertTriangle, Check, X, Brain, BarChart2, Cpu } from 'lucide-react'
import toast from 'react-hot-toast'
import Plot from 'react-plotly.js'

function RiskGauge({ score }) {
  const pct = Math.max(0, Math.min(1, score ?? 0))
  const angle = -150 + pct * 300
  const toRad = d => (d * Math.PI) / 180
  const cx = 100
  const cy = 90
  const r = 70
  const startX = cx + r * Math.cos(toRad(-150))
  const startY = cy + r * Math.sin(toRad(-150))
  const endAngle = -150 + pct * 300
  const endX = cx + r * Math.cos(toRad(endAngle))
  const endY = cy + r * Math.sin(toRad(endAngle))
  const largeArc = pct * 300 > 180 ? 1 : 0
  const color = pct > 0.8 ? '#ef4444' : pct > 0.6 ? '#f97316' : pct > 0.4 ? '#f59e0b' : '#10b981'

  return (
    <svg viewBox="0 0 200 120" className="w-full max-w-xs mx-auto">
      <path
        d={`M ${cx + r * Math.cos(toRad(-150))} ${cy + r * Math.sin(toRad(-150))} A ${r} ${r} 0 1 1 ${cx + r * Math.cos(toRad(150))} ${cy + r * Math.sin(toRad(150))}`}
        fill="none"
        stroke="rgba(51,65,85,0.8)"
        strokeWidth="8"
        strokeLinecap="round"
      />
      {pct > 0.01 && (
        <path
          d={`M ${startX} ${startY} A ${r} ${r} 0 ${largeArc} 1 ${endX} ${endY}`}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${color})` }}
        />
      )}
      <line
        x1={cx}
        y1={cy}
        x2={cx + (r - 15) * Math.cos(toRad(angle))}
        y2={cy + (r - 15) * Math.sin(toRad(angle))}
        stroke={color}
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx={cx} cy={cy} r="5" fill={color} />
      <text x={cx} y={cy + 22} textAnchor="middle" fill="white" fontSize="18" fontWeight="bold">
        {(pct * 100).toFixed(1)}%
      </text>
      <text x="16" y="108" fill="#6b7280" fontSize="8">LOW</text>
      <text x="164" y="108" fill="#6b7280" fontSize="8">CRITICAL</text>
    </svg>
  )
}

function ShapChart({ shapValues }) {
  if (!shapValues) return null
  const entries = Object.entries(shapValues).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 10)
  const labels = entries.map(([k]) => k)
  const values = entries.map(([, v]) => v)
  const colors = values.map(v => (v >= 0 ? '#ef4444' : '#3b82f6'))

  return (
    <Plot
      data={[{
        type: 'bar',
        orientation: 'h',
        y: labels,
        x: values,
        marker: { color: colors },
        hovertemplate: '<b>%{y}</b>: %{x:.4f}<extra></extra>',
      }]}
      layout={{
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        margin: { l: 110, r: 20, t: 10, b: 30 },
        height: 230,
        xaxis: { color: '#94a3b8', gridcolor: 'rgba(51,65,85,0.4)', zeroline: true, zerolinecolor: 'rgba(100,116,139,0.6)' },
        yaxis: { color: '#94a3b8', tickfont: { size: 10 } },
        font: { color: '#94a3b8', size: 11 },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%' }}
    />
  )
}

function DistributionChart({ probabilities }) {
  if (!probabilities) return null
  const entries = Object.entries(probabilities)

  return (
    <Plot
      data={[{
        type: 'bar',
        x: entries.map(([k]) => k),
        y: entries.map(([, v]) => v * 100),
        marker: {
          color: entries.map(([, v]) => `rgba(8,145,178,${0.25 + v * 0.75})`),
          line: { color: '#0891b2', width: 1 },
        },
        hovertemplate: '<b>%{x}</b>: %{y:.1f}%<extra></extra>',
      }]}
      layout={{
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        margin: { l: 30, r: 20, t: 10, b: 50 },
        height: 210,
        xaxis: { color: '#94a3b8', tickfont: { size: 10 } },
        yaxis: { color: '#94a3b8', gridcolor: 'rgba(51,65,85,0.4)', ticksuffix: '%' },
        font: { color: '#94a3b8' },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%' }}
    />
  )
}

const RISK_COLOR = { CRITICAL: 'text-red-400', HIGH: 'text-orange-400', MEDIUM: 'text-yellow-400', LOW: 'text-emerald-400' }
const RISK_BADGE_CLASS = { CRITICAL: 'badge-critical', HIGH: 'badge-high', MEDIUM: 'badge-medium', LOW: 'badge-low' }

export default function InferencePanel({ patientId, onClose }) {
  const [modelType, setModelType] = useState('ML')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [taskId, setTaskId] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [gradcamPreview, setGradcamPreview] = useState(null)

  const role = sessionStorage.getItem('role')

  const isMultimodal = Boolean(result?.model_type === 'MULTIMODAL' || result?.ml_result)
  const mlResult = isMultimodal ? (result?.ml_result ?? null) : (result?.risk_score != null ? result : null)
  const dlResult = isMultimodal ? (result?.dl_result ?? null) : (result?.predicted_class ? result : null)

  const fileToBase64 = file => new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })

  const handleInference = async () => {
    if (role !== 'medico') {
      toast.error('Solo el medico especialista puede ejecutar modelos')
      return
    }

    if (modelType === 'MULTIMODAL' && !selectedFile) {
      toast.error('Para MULTIMODAL debes subir una imagen JPG o PNG')
      return
    }

    setLoading(true)
    setResult(null)
    setTaskId(null)
    try {
      const imageBase64 = selectedFile ? await fileToBase64(selectedFile) : null
      const r = await fetch('/infer', {
        method: 'POST',
        headers: {
          'X-Access-Key': sessionStorage.getItem('accessKey'),
          'X-Permission-Key': sessionStorage.getItem('permissionKey'),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ patient_id: patientId, model_type: modelType, image_base64: imageBase64 }),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        toast.error(err.detail || 'Error ejecutando analisis')
        return
      }
      const d = await r.json()
      setTaskId(d.task_id)
      toast.success('Analisis iniciado')
      pollResults(d.task_id)
    } catch {
      toast.error('Error de conexion')
    } finally {
      setLoading(false)
    }
  }

  const pollResults = tid => {
    pollFallback(tid)
  }

  const pollFallback = tid => {
    let attempts = 0
    const poll = async () => {
      try {
        const r = await fetch(`/infer/${tid}`, {
          headers: {
            'X-Access-Key': sessionStorage.getItem('accessKey'),
            'X-Permission-Key': sessionStorage.getItem('permissionKey'),
          },
        })
        const d = await r.json()
        if (d.status === 'DONE') {
          setResult(d.result)
          toast.success('Analisis completado')
          return
        }
        if (d.status === 'ERROR') {
          setTaskId(null)
          toast.error(d.error_msg || 'Error en el analisis')
          return
        }
        if (++attempts < 30) {
          setTimeout(poll, 3000)
          return
        }
        setTaskId(null)
        toast.error('El analisis tardo demasiado. Intenta de nuevo.')
      } catch {
        setTaskId(null)
        toast.error('Error consultando resultado')
      }
    }
    poll()
  }

  const shapSource = mlResult?.shap_values || dlResult?.shap_values || null
  const distSource = dlResult?.probabilities || mlResult?.probabilities || null
  const riskCategory = mlResult?.risk_category || result?.risk_category || dlResult?.predicted_class
  const riskScore = mlResult?.risk_score ?? result?.risk_score

  useEffect(() => {
    return () => {
      setTaskId(null)
      if (gradcamPreview) URL.revokeObjectURL(gradcamPreview)
    }
  }, [gradcamPreview])

  useEffect(() => {
    const effectiveDlResult = isMultimodal ? dlResult : result
    const effectiveTaskId = effectiveDlResult?.task_id
    if (!effectiveTaskId || !effectiveDlResult?.gradcam_url) return

    let disposed = false
    const loadGradcam = async () => {
      try {
        const response = await fetch(`/fhir/image/${effectiveTaskId}`, {
          headers: {
            'X-Access-Key': sessionStorage.getItem('accessKey'),
            'X-Permission-Key': sessionStorage.getItem('permissionKey'),
          },
        })
        if (!response.ok) return
        const blob = await response.blob()
        const objectUrl = URL.createObjectURL(blob)
        if (disposed) {
          URL.revokeObjectURL(objectUrl)
          return
        }
        setGradcamPreview(current => {
          if (current) URL.revokeObjectURL(current)
          return objectUrl
        })
      } catch {
        // keep textual artifact info if preview cannot be loaded
      }
    }

    loadGradcam()
    return () => { disposed = true }
  }, [dlResult, isMultimodal, result])

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card-clinical space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-bold text-white flex items-center gap-2">
          <Brain className="w-5 h-5 text-purple-400" />
          Panel de Inferencia Clinica
        </h2>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      {!result && !taskId && (
        <>
          <div className="grid grid-cols-3 gap-2">
            {[
              { value: 'ML', label: 'Heart ML', icon: BarChart2, sub: 'Logistic ONNX INT8' },
              { value: 'DL', label: 'Heart DL', icon: Cpu, sub: 'MLP ONNX INT8' },
              { value: 'MULTIMODAL', label: 'Fusion', icon: Zap, sub: 'ML + DL ensemble' },
            ].map(m => (
              <button
                key={m.value}
                type="button"
                onClick={() => setModelType(m.value)}
                className={`p-3 rounded-lg border text-left transition-all ${
                  modelType === m.value
                    ? 'bg-cyan-900/30 border-cyan-500/60'
                    : 'bg-slate-800/30 border-slate-700/60 hover:border-slate-600'
                }`}
              >
                <m.icon className={`w-4 h-4 mb-1.5 ${modelType === m.value ? 'text-cyan-400' : 'text-slate-500'}`} />
                <p className={`text-xs font-semibold ${modelType === m.value ? 'text-cyan-300' : 'text-slate-400'}`}>{m.label}</p>
                <p className="text-xs text-slate-600 mt-0.5">{m.sub}</p>
              </button>
            ))}
          </div>

          {(modelType === 'DL' || modelType === 'MULTIMODAL') && (
            <div className="p-3 rounded-lg bg-slate-800/30 border border-slate-700/60">
              <label className="block text-xs font-semibold text-slate-300 mb-2 uppercase tracking-wider">
                Imagen Clinica (JPG o PNG)
              </label>
              <input
                type="file"
                accept="image/png,image/jpeg"
                onChange={e => setSelectedFile(e.target.files?.[0] ?? null)}
                className="block w-full text-xs text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-cyan-900/30 file:px-3 file:py-2 file:text-cyan-300"
              />
              <p className="text-xs text-slate-500 mt-2">
                {selectedFile
                  ? `Archivo cargado: ${selectedFile.name}`
                  : (modelType === 'MULTIMODAL'
                    ? 'Para MULTIMODAL la imagen es obligatoria.'
                    : 'Para DL la imagen es opcional; si no subes una, se usa imagen sintética.')}
              </p>
            </div>
          )}

          <div className="p-3 rounded-lg bg-amber-900/20 border border-amber-700/40 text-xs text-amber-300 flex items-start gap-2">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            Resultado de apoyo diagnostico. No reemplaza criterio medico.
          </div>

          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            onClick={handleInference}
            disabled={loading}
            className="w-full py-3 rounded-lg font-semibold text-white disabled:opacity-50 flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(135deg,#0891b2,#0e7490)', boxShadow: '0 0 16px rgba(8,145,178,0.3)' }}
          >
            {loading ? <><Loader className="w-4 h-4 animate-spin" /> Ejecutando...</> : <><Zap className="w-4 h-4" /> Ejecutar Analisis</>}
          </motion.button>
        </>
      )}

      {taskId && !result && (
        <div className="text-center py-8 space-y-3">
          <div className="relative w-16 h-16 mx-auto">
            <div className="absolute inset-0 rounded-full border-2 border-cyan-500 border-t-transparent animate-spin" />
            <Brain className="absolute inset-0 m-auto w-6 h-6 text-cyan-400" />
          </div>
          <p className="text-slate-300 font-medium">Procesando analisis...</p>
          <p className="text-xs text-slate-500">Task ID: {taskId?.slice(0, 12)}...</p>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className="p-3 rounded-lg bg-emerald-900/20 border border-emerald-700/40 flex items-center gap-2">
            <Check className="w-4 h-4 text-emerald-400" />
            <p className="text-sm font-semibold text-emerald-300">Analisis completado</p>
          </div>

          {riskScore != null && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-700/40">
                <p className="text-xs text-slate-400 text-center mb-2 font-semibold uppercase tracking-wider">Riesgo Cardiaco</p>
                <RiskGauge score={riskScore} />
              </div>
              <div className="space-y-3 flex flex-col justify-center">
                <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40">
                  <p className="text-xs text-slate-400 mb-1">Categoria</p>
                  <span className={RISK_BADGE_CLASS[riskCategory] || 'badge-low'}>{riskCategory || 'N/A'}</span>
                </div>
                <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40">
                  <p className="text-xs text-slate-400 mb-1">Probabilidad</p>
                  <p className={`text-2xl font-bold ${RISK_COLOR[riskCategory] || 'text-white'}`}>
                    {`${(riskScore * 100).toFixed(1)}%`}
                  </p>
                </div>
              </div>
            </div>
          )}

          {isMultimodal && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40">
                <p className="text-xs text-slate-400 mb-1">Modelo ML</p>
                <p className="text-sm text-cyan-300 font-semibold">{mlResult?.risk_category || 'N/A'}</p>
              </div>
              <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40">
                <p className="text-xs text-slate-400 mb-1">Modelo DL</p>
                <p className="text-sm text-purple-300 font-semibold">{dlResult?.predicted_class || 'N/A'}</p>
              </div>
            </div>
          )}

          {shapSource && (
            <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40">
              <p className="text-xs font-semibold text-slate-300 mb-1 flex items-center gap-1.5">
                <BarChart2 className="w-3.5 h-3.5 text-cyan-400" />
                Explicabilidad de Variables
              </p>
              <p className="text-xs text-slate-500 mb-2">Rojo aumenta riesgo, azul reduce riesgo.</p>
              <ShapChart shapValues={shapSource} />
            </div>
          )}

          {distSource && (
            <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40">
              <p className="text-xs font-semibold text-slate-300 mb-2 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-purple-400" />
                Distribucion por Categoria
              </p>
              <DistributionChart probabilities={distSource} />
            </div>
          )}

          {dlResult?.gradcam_url && (
            <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40">
              <p className="text-xs font-semibold text-slate-300 mb-2">Artefactos de Imagen</p>
              {gradcamPreview && (
                <img src={gradcamPreview} alt="Grad-CAM" className="w-full max-w-sm rounded-lg border border-slate-700/60 mb-3" />
              )}
              <div className="space-y-1 text-xs">
                {dlResult?.image_url && <p className="text-slate-400 break-all">Imagen: {dlResult.image_url}</p>}
                <p className="text-slate-400 break-all">Grad-CAM: {dlResult.gradcam_url}</p>
              </div>
            </div>
          )}

          <button onClick={() => { setResult(null); setTaskId(null) }} className="w-full py-2.5 rounded-lg btn-ghost text-sm">
            Ejecutar nuevo analisis
          </button>
        </div>
      )}
    </motion.div>
  )
}