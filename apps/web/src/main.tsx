import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import { router } from './app/router'
import './styles/global.css'

const container = document.getElementById('root')
if (container === null) {
  throw new Error('未找到挂载点 #root，请检查 index.html')
}

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
