export default async function handler(req, res){
  const backend = process.env.BACKEND_URL || 'http://localhost:5001'
  const r = await fetch(`${backend}/swipe`, {method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify(req.body)})
  const data = await r.json()
  res.status(r.status).json(data)
}
