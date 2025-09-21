export default async function handler(req, res){
  const backend = process.env.BACKEND_URL || 'http://localhost:5001'
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
    return res.status(502).json({ error: 'backend_unavailable', message })
  }
}
