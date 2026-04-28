import { useState } from 'react'
import { motion } from 'framer-motion'
import { Check, X } from 'lucide-react'
import toast from 'react-hot-toast'

export default function RiskReportForm({ riskReport, onSigned }) {
  const [action, setAction] = useState(null)
  const [doctorNotes, setDoctorNotes] = useState('')
  const [rejectionReason, setRejectionReason] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSign = async () => {
    if (doctorNotes.length < 30) {
      toast.error('Las observaciones deben tener al menos 30 caracteres')
      return
    }

    if (action === 'REJECTED' && rejectionReason.length < 20) {
      toast.error('La justificacion de rechazo debe tener al menos 20 caracteres')
      return
    }

    setLoading(true)

    try {
      const accessKey = sessionStorage.getItem('accessKey')
      const permissionKey = sessionStorage.getItem('permissionKey')

      const response = await fetch(`/fhir/RiskAssessment/${riskReport.id}/sign`, {
        method: 'PATCH',
        headers: {
          'X-Access-Key': accessKey,
          'X-Permission-Key': permissionKey,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          doctor_action: action,
          doctor_notes: doctorNotes,
          rejection_reason: rejectionReason || null,
        }),
      })

      if (response.ok) {
        toast.success('RiskReport firmado')
        onSigned()
      } else {
        toast.error('Error al firmar el reporte')
      }
    } catch {
      toast.error('Error de conexion')
    } finally {
      setLoading(false)
    }
  }

  const notesLength = doctorNotes.length
  const rejectionLength = rejectionReason.length

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card-clinical space-y-4">
      <h2 className="text-xl font-bold">Firma del RiskReport</h2>

      <div>
        <label className="block text-sm font-medium text-slate-200 mb-2">Observaciones Clinicas (minimo 30 caracteres)</label>
        <textarea
          value={doctorNotes}
          onChange={e => setDoctorNotes(e.target.value)}
          placeholder="Ingrese sus observaciones clinicas..."
          className="w-full px-4 py-2 rounded-lg bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-teal-500 transition-colors h-24 resize-none"
        />
        <p className={`text-xs mt-1 ${notesLength >= 30 ? 'text-green-400' : 'text-slate-500'}`}>
          {notesLength}/30 caracteres {notesLength >= 30 && 'OK'}
        </p>
      </div>

      <div className="flex gap-4">
        <button
          onClick={() => setAction('ACCEPTED')}
          className={`flex-1 py-3 rounded-lg font-semibold flex items-center justify-center gap-2 transition-colors ${
            action === 'ACCEPTED' ? 'bg-green-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
          }`}
        >
          <Check className="w-4 h-4" />
          Aceptar Diagnostico
        </button>
        <button
          onClick={() => setAction('REJECTED')}
          className={`flex-1 py-3 rounded-lg font-semibold flex items-center justify-center gap-2 transition-colors ${
            action === 'REJECTED' ? 'bg-red-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
          }`}
        >
          <X className="w-4 h-4" />
          Rechazar Diagnostico
        </button>
      </div>

      {action === 'REJECTED' && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
          <label className="block text-sm font-medium text-slate-200 mb-2">Justificacion del Rechazo (minimo 20 caracteres)</label>
          <textarea
            value={rejectionReason}
            onChange={e => setRejectionReason(e.target.value)}
            placeholder="Explique por que rechaza este diagnostico..."
            className="w-full px-4 py-2 rounded-lg bg-slate-800/50 border border-red-700/50 text-white placeholder-slate-500 focus:outline-none focus:border-red-500 transition-colors h-20 resize-none"
          />
          <p className={`text-xs mt-1 ${rejectionLength >= 20 ? 'text-green-400' : 'text-slate-500'}`}>
            {rejectionLength}/20 caracteres {rejectionLength >= 20 && 'OK'}
          </p>
        </motion.div>
      )}

      <button
        onClick={handleSign}
        disabled={loading || !action || doctorNotes.length < 30 || (action === 'REJECTED' && rejectionReason.length < 20)}
        className="w-full py-3 rounded-lg bg-teal-600 text-white font-semibold hover:bg-teal-700 disabled:bg-slate-700 disabled:text-slate-500 transition-colors"
      >
        {loading ? 'Firmando...' : 'Firmar RiskReport'}
      </button>

      <p className="text-xs text-slate-500 text-center">Al firmar, confirma que reviso el diagnostico de IA y lo valida clinicamente.</p>
    </motion.div>
  )
}