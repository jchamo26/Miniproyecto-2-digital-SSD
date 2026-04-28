import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import App from './App'
import Login from './views/Login'
import Dashboard from './views/Dashboard'
import PatientDetail from './views/PatientDetail'
import AdminPanel from './views/AdminPanel'
import './index.css'

function RequireAuth({ children }) {
  const token = sessionStorage.getItem('token')
  return token ? children : <Navigate to="/login" replace />
}

function RequireRole({ roles, children }) {
  const role = sessionStorage.getItem('role')
  return roles.includes(role) ? children : <Navigate to="/dashboard" replace />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Toaster position="top-right" />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/patients/:id" element={<RequireAuth><PatientDetail /></RequireAuth>} />
        <Route path="/admin" element={<RequireAuth><RequireRole roles={['admin']}><AdminPanel /></RequireRole></RequireAuth>} />
        <Route path="/" element={<Navigate to="/dashboard" />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
