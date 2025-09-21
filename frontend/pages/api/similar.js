export default async function handler(req, res){
  const backend = process.env.BACKEND_URL || 'http://localhost:5001'
  try{
    const qs = new URLSearchParams()
    if(req.query.product_id) qs.set('product_id', req.query.product_id)
    if(req.query.image_url) qs.set('image_url', req.query.image_url)
    if(req.query.k) qs.set('k', req.query.k)
    const url = `${backend}/similar${qs.toString() ? '?'+qs.toString() : ''}`
    const r = await fetch(url)
    const data = await r.json()
    return res.status(r.status).json(data)
  }catch(err){
    console.error('Error proxying /similar to backend', err)
    const message = err && err.message ? err.message : String(err)
    return res.status(502).json({ error: 'backend_unavailable', message })
  }
}
