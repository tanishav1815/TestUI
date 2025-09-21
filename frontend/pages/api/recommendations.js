export default async function handler(req, res){
  // prefer explicit addresses to avoid localhost/IPv6 issues. Allow BACKEND_URL env
  // to override. If not set, try 127.0.0.1 then the LAN IP observed on dev machine.
  const backend = process.env.BACKEND_URL || 'http://127.0.0.1:5001' || 'http://10.157.205.243:5001'
  try{
    const qs = new URLSearchParams()
  if(req.query.user_id) qs.set('user_id', req.query.user_id)
  if(req.query.category) qs.set('category', req.query.category)
  if(req.query.color) qs.set('color', req.query.color)
  if(req.query.location) qs.set('location', req.query.location)
  if(req.query.min_price) qs.set('min_price', req.query.min_price)
  if(req.query.max_price) qs.set('max_price', req.query.max_price)
    const url = `${backend}/recommendations${qs.toString() ? '?'+qs.toString() : ''}`
    const r = await fetch(url)
    const data = await r.json()
    return res.status(r.status).json(data)
  }catch(err){
    console.error('Error proxying /recommendations to backend', err)
    const message = err && err.message ? err.message : String(err)
    // include stack in logs and return a concise error to the client
    return res.status(502).json({ error: 'backend_unavailable', message })
  }
}
