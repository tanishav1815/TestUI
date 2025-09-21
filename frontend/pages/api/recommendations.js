export default async function handler(req, res){
  const backend = process.env.BACKEND_URL || 'http://localhost:5001'
  try{
    const r = await fetch(`${backend}/recommendations`)
    const data = await r.json()
    return res.status(r.status).json(data)
  }catch(err){
    console.error('Error proxying /recommendations to backend', err)
    const message = err && err.message ? err.message : String(err)
    return res.status(502).json({ error: 'backend_unavailable', message })
  }
}
