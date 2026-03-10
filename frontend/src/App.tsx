import { Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="min-h-screen bg-sentinel-bg text-sentinel-text">
      <Outlet />
    </div>
  )
}
