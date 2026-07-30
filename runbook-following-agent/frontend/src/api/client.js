import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

export const uploadRunbook = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const parseRunbook = (filename) =>
  api.post('/parse', { filename })

export const startExecution = (filename, sessionId = null) =>
  api.post('/execute', { filename, session_id: sessionId })

export const confirmStep = (sessionId, step, approved) =>
  api.post('/execute/confirm', { session_id: sessionId, step, approved })

export const pauseExecution = (sessionId) =>
  api.post('/execute/pause', { session_id: sessionId })

export const resumeExecution = (sessionId) =>
  api.post('/execute/resume', { session_id: sessionId })

export const retryStep = (sessionId, step) =>
  api.post('/execute/retry', { session_id: sessionId, step })

export const getExecutionState = (sessionId) =>
  api.get(`/execute/state/${sessionId}`)

export const getLogs = (sessionId = null) =>
  api.get('/logs', { params: sessionId ? { session_id: sessionId } : {} })

export const getReport = (sessionId) =>
  api.get('/report', { params: { session_id: sessionId } })

export const downloadReportPdf = (sessionId) =>
  api.get('/report/pdf', {
    params: { session_id: sessionId },
    responseType: 'blob',
  })

export default api
