/* eslint-disable react-refresh/only-export-components */
import { createBrowserRouter } from 'react-router-dom'
import App from './App'

// Placeholder page components — replaced in later tasks
const PlaygroundPage = () => (
  <div className="p-8 text-sentinel-text">
    <h1 className="text-2xl font-semibold">PlaygroundPage</h1>
  </div>
)

const AnalyticsDashboardPage = () => (
  <div className="p-8 text-sentinel-text">
    <h1 className="text-2xl font-semibold">AnalyticsDashboardPage</h1>
  </div>
)

const RequestExplorerPage = () => (
  <div className="p-8 text-sentinel-text">
    <h1 className="text-2xl font-semibold">RequestExplorerPage</h1>
  </div>
)

const KnowledgeBasePage = () => (
  <div className="p-8 text-sentinel-text">
    <h1 className="text-2xl font-semibold">KnowledgeBasePage</h1>
  </div>
)

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      {
        index: true,
        element: <PlaygroundPage />,
      },
      {
        path: 'analytics',
        element: <AnalyticsDashboardPage />,
      },
      {
        path: 'requests',
        element: <RequestExplorerPage />,
      },
      {
        path: 'kb',
        element: <KnowledgeBasePage />,
      },
    ],
  },
])
