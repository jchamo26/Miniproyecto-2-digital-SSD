import { useState } from 'react'
import { motion } from 'framer-motion'

const HABEAS_DATA_TEXT = `POLÍTICA DE PRIVACIDAD Y PROTECCIÓN DE DATOS PERSONALES
Ley 1581/2012 - Protección de Datos Personales en Colombia

ACEPTACIÓN DE TÉRMINOS:
Al hacer clic en "Acepto", usted reconoce que:

1. Sus datos personales y de salud serán tratados de acuerdo con la Ley 1581/2012 de Colombia.
2. Solo serán utilizados para fines clínicos y de investigación médica.
3. Su información será cifrada con AES-256 y almacenada de forma segura.
4. Tiene derecho a acceder, rectificar, cancelar u oponerse al tratamiento de sus datos (Derechos ARCO).
5. Los datos no serán compartidos con terceros sin su consentimiento explícito.
6. Este consentimiento es revocable en cualquier momento.

RESPONSABLE DEL TRATAMIENTO:
Sistema Clínico Digital - UAO
Fecha: 09/04/2026

CONFIRME SU ACEPTACIÓN PARA CONTINUAR`

export default function HabeasDataModal({ onAccept }) {
  const [accepted, setAccepted] = useState(false)
  const [showModal, setShowModal] = useState(true)

  if (!showModal) return null

  const handleAccept = () => {
    onAccept()
    setShowModal(false)
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-8"
      >
        <h2 className="text-2xl font-bold text-white mb-4">
          Política de Habeas Data
        </h2>
        
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 mb-6 text-sm text-slate-300 whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">
          {HABEAS_DATA_TEXT}
        </div>

        <div className="space-y-4">
          <label className="flex items-start space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              className="w-5 h-5 mt-1 accent-teal-600"
            />
            <span className="text-sm text-slate-300">
              Acepto la política de privacidad y protección de datos personales según la Ley 1581/2012
            </span>
          </label>

          <button
            onClick={handleAccept}
            disabled={!accepted}
            className="w-full py-3 rounded-lg bg-teal-600 text-white font-semibold hover:bg-teal-700 disabled:bg-slate-700 disabled:text-slate-500 transition-colors"
          >
            ✅ Acepto y Continuar
          </button>

          <p className="text-xs text-slate-500 text-center">
            Al aceptar, su consentimiento será registrado con marca de tiempo e IP
          </p>
        </div>
      </motion.div>
    </motion.div>
  )
}
