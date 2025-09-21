import { useEffect, useRef, useState } from 'react'
import useSWR from 'swr'

const fetcher = (url) => fetch(url).then(r=>r.json())

function Card({ item, onSwipe }){
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
  const {data, error, mutate} = useSWR('/api/recommendations', fetcher, {refreshInterval:0})
  const [stack, setStack] = useState([])

  useEffect(()=>{
    // only update stack when data.items is an array
    if(data && Array.isArray(data.items)) setStack(data.items)
  },[data])

  async function handleSwipe(action, item){
    // send to backend
    try{
      await fetch('/api/swipe', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({action, user_id: USER_ID, item_id: item.id, image: item.image})})
    }catch(e){
      console.error(e)
    }
    // remove top item
    setStack(s => Array.isArray(s) ? s.slice(1) : [])
  }

  return (
    <div className="container">
      <h1>Product Swipe</h1>
      <div className="deck">
        {(Array.isArray(stack) && stack.length===0) && <p>Loading or no more items</p>}
        {(Array.isArray(stack) ? stack.slice(0,3) : []).map((it,idx)=> (
          <Card key={it.id} item={it} onSwipe={handleSwipe} />
        ))}
      </div>
    </div>
  )
}
