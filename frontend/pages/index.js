import { useEffect, useRef, useState } from 'react'
import useSWR from 'swr'

const fetcher = (url) => fetch(url).then(r=>r.json())
// When running locally, allow the client to call the Flask backend directly
const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:5001'

function Card({ item, onSwipe, favorites, toggleFavorite }){
  const ref = useRef()
  const pos = useRef({x:0,y:0})
      const overlayRef = useRef()
  useEffect(()=>{
    const el = ref.current
    if(!el) return
    let start = null
    let dragging = false
    let origin = {x:0,y:0}

    function pointerDown(e){
      dragging = true
      start = {x: e.clientX, y: e.clientY}
      origin = {x: el.offsetLeft, y: el.offsetTop}
      el.setPointerCapture(e.pointerId)
    }
    function pointerMove(e){
      if(!dragging) return
      const dx = e.clientX - start.x
      const dy = e.clientY - start.y
      pos.current = {x:dx,y:dy}
      el.style.transform = `translate(${dx}px, ${dy}px) rotate(${dx/20}deg)`
      el.style.transition = 'transform 0s'
        // show overlay
        if(overlayRef.current){
          overlayRef.current.style.opacity = Math.min(1, Math.abs(dx)/120)
          overlayRef.current.textContent = dx>0? 'LIKE' : 'NOPE'
          overlayRef.current.style.background = dx>0? 'rgba(0,200,120,0.12)' : 'rgba(200,0,80,0.12)'
        }
    }
    function pointerUp(e){
      if(!dragging) return
      dragging = false
      const dx = pos.current.x
      // threshold
      const threshold = 120
      if(dx > threshold){
        // like
        el.style.transition = 'transform 300ms ease-out'
        el.style.transform = `translate(${window.innerWidth}px, ${pos.current.y}px)`
        onSwipe('like', item)
      } else if(dx < -threshold){
        el.style.transition = 'transform 300ms ease-out'
        el.style.transform = `translate(-${window.innerWidth}px, ${pos.current.y}px)`
        onSwipe('dislike', item)
      } else {
        el.style.transition = 'transform 200ms ease-out'
        el.style.transform = 'translate(0px,0px)'
      }
        // hide overlay after interaction
        if(overlayRef.current){
          overlayRef.current.style.opacity = 0
        }
    }

    el.addEventListener('pointerdown', pointerDown)
    window.addEventListener('pointermove', pointerMove)
    window.addEventListener('pointerup', pointerUp)

    return ()=>{
      el.removeEventListener('pointerdown', pointerDown)
      window.removeEventListener('pointermove', pointerMove)
      window.removeEventListener('pointerup', pointerUp)
    }
  },[item,onSwipe])

  return (
    <div ref={ref} className="card">
          <button className={`fav ${favorites && favorites.includes(item.id)? 'active':''}`} onClick={(e)=>{ e.stopPropagation(); toggleFavorite(item.id) }}>{favorites && favorites.includes(item.id)? '★' : '☆'}</button>
          <div className="overlay" ref={overlayRef} />
      <img src={item.image} alt={item.name} />
      <div className="meta">
        <h3>{item.name}</h3>
        <p>{item.price}</p>
      </div>
    </div>
  )
}

export default function Home(){
  const USER_ID = process.env.NEXT_PUBLIC_USER_ID || 'anonymous'
  const [selectedCategory, setSelectedCategory] = useState('')
  const [colorFilter, setColorFilter] = useState('')
  const [locationFilter, setLocationFilter] = useState('')
  const [minPriceFilter, setMinPriceFilter] = useState('')
  const [maxPriceFilter, setMaxPriceFilter] = useState('')
  const swrKey = () => {
    const params = new URLSearchParams()
    if(selectedCategory) params.set('category', selectedCategory)
    if(colorFilter) params.set('color', colorFilter)
    if(locationFilter) params.set('location', locationFilter)
    if(minPriceFilter) params.set('min_price', minPriceFilter)
    if(maxPriceFilter) params.set('max_price', maxPriceFilter)
    const qs = params.toString()
    // call backend directly from the browser (avoids server-side proxy issues)
    return `${BACKEND}/recommendations${qs? '?'+qs : ''}`
  }
  const {data, error, mutate} = useSWR(swrKey, fetcher, {refreshInterval:0})
  const {data:catData} = useSWR(`${BACKEND}/categories`, fetcher)
  const [stack, setStack] = useState([])
  const deckRef = useRef()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [moreRecs, setMoreRecs] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [moreRecsLoading, setMoreRecsLoading] = useState(false)
  const [favorites, setFavorites] = useState(() => {
    try{ return JSON.parse(localStorage.getItem('favorites')||'[]') }catch(e){ return [] }
  })
  useEffect(()=>{
    try{ const saved = JSON.parse(localStorage.getItem('favorites')||'[]'); setFavorites(saved) }catch(e){}
  },[])

  function toggleFavorite(id){
    setFavorites(prev => {
      const next = prev.includes(id) ? prev.filter(x=>x!==id) : prev.concat([id])
      try{ localStorage.setItem('favorites', JSON.stringify(next)) }catch(e){}
      return next
    })
  }

  useEffect(()=>{
    // only update stack when data.items is an array
    if(data && Array.isArray(data.items)) setStack(data.items)
  },[data])

  useEffect(()=>{
    // when category changes, reset stack and let SWR fetch
    if(typeof selectedCategory !== 'undefined'){
      setStack([])
    }
  },[selectedCategory])

  async function handleSwipe(action, item){
    // send to backend
    try{
      const resp = await fetch(`${BACKEND}/swipe`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({action, user_id: USER_ID, item_id: item.id, image: item.image})})
      // if backend returns recommendations, push them to top of stack
      if(resp && resp.ok){
        const body = await resp.json()
        if(body && Array.isArray(body.recommendations) && body.recommendations.length>0){
          setStack(s => {
            const curr = Array.isArray(s)? s : []
            // prepend new recommendations while keeping the remaining
            return body.recommendations.concat(curr.slice(1))
          })
        }
      }
    }catch(e){
      console.error(e)
    }
    // remove top item
    setStack(s => Array.isArray(s) ? s.slice(1) : [])
  }

  async function doSearch(){
    if(!searchQuery) return setSearchResults([])
    setSearchLoading(true)
    try{
  const res = await fetch(`${BACKEND}/search?q=${encodeURIComponent(searchQuery)}&color=${encodeURIComponent(colorFilter||'')}&location=${encodeURIComponent(locationFilter||'')}`)
      const data = await res.json()
      setSearchResults(Array.isArray(data.items)? data.items : [])
    }catch(e){
      console.error(e)
    }finally{
      setSearchLoading(false)
    }
  }

  async function loadSimilar(product_id){
    setMoreRecsLoading(true)
    try{
  const res = await fetch(`${BACKEND}/similar?product_id=${product_id}&k=8`)
      const data = await res.json()
      setMoreRecs(Array.isArray(data.items)? data.items : [])
    }catch(e){
      console.error(e)
    }finally{
      setMoreRecsLoading(false)
    }
  }

  function doButtonSwipe(action){
    const top = Array.isArray(stack) && stack[0]
    if(!top) return
    // animate top card off-screen to mimic swipe
    const el = deckRef.current && deckRef.current.querySelector('.card')
    if(el){
      const y = 0
      const off = window.innerWidth || 800
      el.style.transition = 'transform 350ms ease-out'
      if(action === 'like'){
        el.style.transform = `translate(${off}px, ${y}px) rotate(20deg)`
      } else {
        el.style.transform = `translate(-${off}px, ${y}px) rotate(-20deg)`
      }
    }
    // wait for animation then perform the same logic as a swipe
    setTimeout(()=> handleSwipe(action, top), 360)
  }

  // keyboard shortcuts for left/right
  useEffect(()=>{
    function onKey(e){
      if(e.key === 'ArrowLeft') doButtonSwipe('dislike')
      if(e.key === 'ArrowRight') doButtonSwipe('like')
    }
    window.addEventListener('keydown', onKey)
    return ()=> window.removeEventListener('keydown', onKey)
  },[stack])

  return (
    <div className="container">
      <div className="category-bar" style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:12}}>
        <button className={`cat ${selectedCategory===''? 'active':''}`} onClick={()=>setSelectedCategory('')}>All</button>
        {(catData && Array.isArray(catData.categories) ? catData.categories : []).map(c=> (
          <button key={c} className={`cat ${selectedCategory===c? 'active':''}`} onClick={()=>setSelectedCategory(c)}>{c}</button>
        ))}
      </div>
      <div style={{display:'flex',gap:8,alignItems:'center',marginBottom:12}}>
        <input placeholder="color" value={colorFilter} onChange={e=>setColorFilter(e.target.value)} />
        <input placeholder="location" value={locationFilter} onChange={e=>setLocationFilter(e.target.value)} />
        <input placeholder="min price" type="number" value={minPriceFilter} onChange={e=>setMinPriceFilter(e.target.value)} />
        <input placeholder="max price" type="number" value={maxPriceFilter} onChange={e=>setMaxPriceFilter(e.target.value)} />
        <button onClick={()=>{ setSelectedCategory(''); setColorFilter(''); setLocationFilter(''); setMinPriceFilter(''); setMaxPriceFilter(''); mutate(); }}>Clear Filters</button>
      </div>
      <h1>Product Swipe</h1>
      <div style={{display:'flex',gap:12,marginBottom:12,alignItems:'center'}}>
        <input placeholder="Search products" value={searchQuery} onChange={e=>setSearchQuery(e.target.value)} style={{flex:1}} />
        <button onClick={doSearch}>Search</button>
      </div>
      <div className="deck" ref={deckRef}>
        {(Array.isArray(stack) && stack.length===0) && <p>Loading or no more items</p>}
        {(Array.isArray(stack) ? stack.slice(0,3) : []).map((it,idx)=> (
          <Card key={it.id} item={it} onSwipe={handleSwipe} favorites={favorites} toggleFavorite={toggleFavorite} />
        ))}
      </div>
      <div style={{marginTop:12}}>
        <h3>More Recommendations</h3>
        <div style={{display:'flex',gap:8,overflowX:'auto',padding:'8px 0'}}>
          {moreRecsLoading && <div className="spinner" />}
          {moreRecs.map(m=> (
            <div key={m.id} style={{width:140,minWidth:140,cursor:'pointer',position:'relative'}}>
              <div style={{position:'relative'}} onClick={()=>{
                // put selected similar item on top of stack and load more similar
                setStack(s => [m].concat(Array.isArray(s)?s:[]))
                loadSimilar(m.id)
              }}>
                <img src={m.image} alt={m.name} style={{width:'100%',height:100,objectFit:'cover',borderRadius:6}} />
              </div>
              <button className={`fav ${favorites.includes(m.id)? 'active':''}`} onClick={(evt)=>{ evt.stopPropagation(); toggleFavorite(m.id) }}>
                {favorites.includes(m.id)? '★' : '☆'}
              </button>
              <div style={{fontSize:12}}>{m.name}</div>
              <div style={{fontSize:11,color:'#666'}}>{m.price}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{marginTop:12}}>
        {searchResults.length>0 && (
          <div>
            <h3>Search Results</h3>
            <div>
              {searchLoading && <div style={{display:'flex',justifyContent:'center',padding:12}}><div className="spinner" /></div>}
              <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(180px,1fr))',gap:12}}>
                {searchResults.map(s=> (
                  <div key={s.id} className="result-card" style={{position:'relative'}} onClick={()=>{
                    // push selected search item to top of stack and fetch similar
                    setStack(curr => [s].concat(Array.isArray(curr)?curr:[]))
                    loadSimilar(s.id)
                  }}>
                    <img src={s.image} alt={s.name} className="thumb" />
                    <button className={`fav ${favorites.includes(s.id)? 'active':''}`} onClick={(evt)=>{ evt.stopPropagation(); toggleFavorite(s.id) }}>{favorites.includes(s.id)? '★' : '☆'}</button>
                    <div style={{fontWeight:600}}>{s.name}</div>
                    <div style={{color:'#666'}}>{s.price}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="controls">
        <button className="btn btn-dislike" aria-label="dislike" onClick={()=>doButtonSwipe('dislike')}>Nope</button>
        <button className="btn btn-like" aria-label="like" onClick={()=>doButtonSwipe('like')}>Like</button>
      </div>
    </div>
  )
}
