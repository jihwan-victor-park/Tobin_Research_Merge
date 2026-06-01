import { useEffect, useRef, useState } from 'react'
import Globe from 'react-globe.gl'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ACCENT = '#00356B'

// Static lat/lng for top countries
const COUNTRY_COORDS = {
  'United States':        { lat: 37.09,  lng: -95.71 },
  'United Kingdom':       { lat: 55.38,  lng: -3.44  },
  'Canada':               { lat: 56.13,  lng: -106.35 },
  'India':                { lat: 20.59,  lng: 78.96  },
  'Israel':               { lat: 31.05,  lng: 34.85  },
  'Germany':              { lat: 51.17,  lng: 10.45  },
  'France':               { lat: 46.23,  lng: 2.21   },
  'Australia':            { lat: -25.27, lng: 133.78 },
  'Singapore':            { lat: 1.35,   lng: 103.82 },
  'Netherlands':          { lat: 52.13,  lng: 5.29   },
  'Sweden':               { lat: 60.13,  lng: 18.64  },
  'Switzerland':          { lat: 46.82,  lng: 8.23   },
  'Brazil':               { lat: -14.24, lng: -51.93 },
  'Spain':                { lat: 40.46,  lng: -3.75  },
  'Finland':              { lat: 61.92,  lng: 25.75  },
  'Denmark':              { lat: 56.26,  lng: 9.50   },
  'Norway':               { lat: 60.47,  lng: 8.47   },
  'Japan':                { lat: 36.20,  lng: 138.25 },
  'South Korea':          { lat: 35.91,  lng: 127.77 },
  'China':                { lat: 35.86,  lng: 104.20 },
  'Estonia':              { lat: 58.60,  lng: 25.01  },
  'Poland':               { lat: 51.92,  lng: 19.15  },
  'Ireland':              { lat: 53.14,  lng: -8.24  },
  'Mexico':               { lat: 23.63,  lng: -102.55 },
  'Colombia':             { lat: 4.57,   lng: -74.30 },
  'Nigeria':              { lat: 9.08,   lng: 8.68   },
  'South Africa':         { lat: -30.56, lng: 22.94  },
  'Kenya':                { lat: -0.02,  lng: 37.91  },
  'Egypt':                { lat: 26.82,  lng: 30.80  },
  'United Arab Emirates': { lat: 23.42,  lng: 53.85  },
  'Pakistan':             { lat: 30.38,  lng: 69.35  },
  'Bangladesh':           { lat: 23.68,  lng: 90.36  },
  'Indonesia':            { lat: -0.79,  lng: 113.92 },
  'Portugal':             { lat: 39.40,  lng: -8.22  },
  'Italy':                { lat: 41.87,  lng: 12.57  },
  'Austria':              { lat: 47.52,  lng: 14.55  },
  'Belgium':              { lat: 50.50,  lng: 4.47   },
  'Czech Republic':       { lat: 49.82,  lng: 15.47  },
  'Romania':              { lat: 45.94,  lng: 24.97  },
  'Ukraine':              { lat: 48.38,  lng: 31.17  },
  'Turkey':               { lat: 38.96,  lng: 35.24  },
  'Argentina':            { lat: -38.42, lng: -63.62 },
  'Chile':                { lat: -35.68, lng: -71.54 },
  'New Zealand':          { lat: -40.90, lng: 174.89 },
  'Philippines':          { lat: 12.88,  lng: 121.77 },
  'Vietnam':              { lat: 14.06,  lng: 108.28 },
  'Thailand':             { lat: 15.87,  lng: 100.99 },
  'Malaysia':             { lat: 4.21,   lng: 101.98 },
  'Hong Kong':            { lat: 22.32,  lng: 114.17 },
  'Taiwan':               { lat: 23.70,  lng: 121.00 },
  'Greece':               { lat: 39.07,  lng: 21.82  },
  'Hungary':              { lat: 47.16,  lng: 19.50  },
  'Latvia':               { lat: 56.88,  lng: 24.60  },
  'Lithuania':            { lat: 55.17,  lng: 23.88  },
}

const GLOBE_HEIGHT = 500

export default function GlobeView() {
  const wrapperRef = useRef(null)
  const globeRef = useRef(null)
  const [width, setWidth] = useState(0)
  const [locations, setLocations] = useState([])
  const [error, setError] = useState(null)

  // Measure container width with ResizeObserver
  useEffect(() => {
    if (!wrapperRef.current) return
    const ro = new ResizeObserver(entries => {
      setWidth(Math.floor(entries[0].contentRect.width))
    })
    ro.observe(wrapperRef.current)
    return () => ro.disconnect()
  }, [])

  // Fetch location data
  useEffect(() => {
    fetch(`${API}/api/stats/locations`)
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
      .then(data => {
        const points = data
          .map(d => {
            const coords = COUNTRY_COORDS[d.country]
            if (!coords) return null
            return { ...coords, label: d.country, count: d.count }
          })
          .filter(Boolean)
        console.log('[GlobeView] locations loaded:', points.length, 'points, top:', points[0])
        setLocations(points)
      })
      .catch(e => { console.error('[GlobeView] fetch error:', e); setError(e.message) })
  }, [])

  // Wire up auto-rotate once globe mounts
  useEffect(() => {
    if (!globeRef.current) return
    const controls = globeRef.current.controls()
    controls.autoRotate = true
    controls.autoRotateSpeed = 0.4
    globeRef.current.pointOfView({ lat: 30, lng: -40, altitude: 2.2 }, 800)
  }, [locations, width])

  const maxCount = locations.length ? Math.max(...locations.map(p => p.count)) : 1

  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10,
      padding: '20px 24px',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 14 }}>
        AI Startup Locations
      </div>
      <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 16 }}>
        Companies with ai_score ≥ 0.1 · point size scales with count · drag to rotate
      </div>
      {error && <p style={{ color: '#dc2626', fontSize: 13 }}>Failed to load: {error}</p>}
      {!error && locations.length === 0 && (
        <p style={{ color: '#9ca3af', fontSize: 13 }}>Loading…</p>
      )}

      {/* Measure wrapper — must have explicit height so Globe can calculate dimensions */}
      <div
        ref={wrapperRef}
        style={{ height: GLOBE_HEIGHT, borderRadius: 8, overflow: 'hidden', background: '#f8f9fa' }}
      >
        {width > 0 && locations.length > 0 && (
          <Globe
            ref={globeRef}
            width={width}
            height={GLOBE_HEIGHT}
            backgroundColor="rgba(0,0,0,0)"
            globeImageUrl="//unpkg.com/three-globe/example/img/earth-day.jpg"
            atmosphereColor="#a8c4e0"
            atmosphereAltitude={0.12}
            pointsData={locations}
            pointLat={d => d.lat}
            pointLng={d => d.lng}
            pointColor={() => ACCENT}
            pointAltitude={d => 0.01 + (d.count / maxCount) * 0.10}
            pointRadius={d => 0.25 + (d.count / maxCount) * 1.4}
            pointLabel={d =>
              `<div style="font-family:Inter,sans-serif;font-size:13px;background:#fff;border:1px solid #e5e7eb;padding:6px 10px;border-radius:6px;color:#111827;box-shadow:0 2px 8px rgba(0,0,0,0.08)"><strong>${d.label}</strong><br/>${d.count.toLocaleString()} AI companies</div>`
            }
          />
        )}
      </div>
    </div>
  )
}
